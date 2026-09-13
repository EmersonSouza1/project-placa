# Reconhecimento de placas e permanência em docas

Guia de contribuição: [AGENTS.md](AGENTS.md). Documentação detalhada de arquitetura,
regras de negócio, contratos e operação: [.ia/README.md](.ia/README.md).

POC de **uma câmera / uma doca**, com serviço Python de visão, API .NET 10 e
PostgreSQL 17. O primeiro objetivo é validar eventos de entrada/saída por tracking
e zonas. Uma placa desconhecida não impede registrar a movimentação.

O modo padrão é uma **simulação de trajetórias**: não exige câmera, GPU ou modelos.
Os adaptadores de vídeo implementam YOLO + ByteTrack e detector de placas +
PaddleOCR, mas precisam de vídeo e pesos para validação real.

```mermaid
flowchart LR
    C[RTSP ou vídeo] --> V[YOLO veículos + ByteTrack]
    S[Trajetórias simuladas] --> Z[Zonas + estados]
    V --> Z
    V --> P[YOLO placas + PaddleOCR]
    P --> A[Consenso por track]
    A --> Z
    Z --> Q[Outbox SQLite persistente]
    Q -->|POST /dock-events| API[API .NET]
    API --> DB[(PostgreSQL: eventos e permanências)]
```

## Executar a simulação

Requer Docker com Compose e containers Linux. No PowerShell, a partir da raiz:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
docker compose up --build -d
docker compose logs -f vision api
```

Em outro terminal:

```powershell
Invoke-RestMethod http://localhost:5080/health
Invoke-RestMethod http://localhost:5080/dock-events
Invoke-RestMethod http://localhost:5080/dock-stays
```

Na primeira execução, com a zona padrão, espere **4 eventos / 2 permanências**:

| Track | Eventos | Permanência | Placa |
|---|---|---|---|
| 1 | `entered`, `exited` | `completed`, 6 segundos | `ABC1D23`, observações sintéticas |
| 2 | `observed_inside`, `tracking_lost` | `interrupted`, duração desconhecida | `null` |

A simulação executa uma vez e mantém o processo ativo para entregar pendências.
`docker compose restart vision` cria uma nova simulação, com novos identificadores.
Os dados anteriores permanecem no banco. `docker compose down` para os serviços
preservando os volumes. Nenhuma imagem é armazenada nesta versão.

## Estrutura

- `services/vision/dock_vision/domain.py`: zonas, estados e consenso de placas, sem dependências externas.
- `services/vision/dock_vision/pipeline.py`: captura RTSP/vídeo e adaptadores de inferência.
- `services/vision/dock_vision/outbox.py`: entrega HTTP e recuperação após indisponibilidade.
- `services/api`: API .NET, eventos imutáveis e projeção transacional de permanências.
- `config/zone.json`: polígono e parâmetros da doca.
- `tests/api_smoke.py`: verificações de integração contra a API e o PostgreSQL ativos.

## Estados e eventos

A posição usada é o centro inferior da caixa do veículo, normalizado entre 0 e 1.
O polígono inclui a borda. A mudança de zona precisa persistir por
`confirmation_seconds`; frames sem detecção reiniciam essa confirmação.

| Situação | Evento | Efeito |
|---|---|---|
| Fora confirmado → dentro confirmado | `entered` | Abre visita com entrada conhecida |
| Primeira observação já dentro, confirmada | `observed_inside` | Abre visita sem afirmar quando ocorreu a entrada |
| Dentro confirmado → fora confirmado | `exited` | Fecha visita com saída observada |
| Track interno ausente por `lost_after_seconds` | `tracking_lost` | Interrompe visita; não representa saída física |
| Desconexão RTSP / fim de vídeo / encerramento normal | `tracking_lost` | Interrompe visitas ainda abertas |

Cada ocupação recebe um `visit_id`; reentradas recebem outro. `stream_id` identifica
a execução do worker, para que IDs numéricos reutilizados pelo tracker não colidam
entre reinícios. Na reconexão, o tracker é recriado e os estados anteriores são limpos.

`duration_seconds` só existe para o par `entered` + `exited`. Para uma visita
iniciada com `observed_inside`, os horários indicam o intervalo observado, mas não
a duração total. `ended_at` em uma visita interrompida é o horário da interrupção.
Uma saída recebida antes da entrada gera `awaiting_start`; a entrada posterior
recalcula a mesma permanência. Horários contraditórios são rejeitados.

## Contrato HTTP

`POST /dock-events`, JSON, todos os campos abaixo são obrigatórios; placa e
confiança podem ser `null` juntas. Datas usam ISO 8601 com UTC/offset.

```json
{
  "event_id": "976925f7-f20e-41f9-b7b4-d7720332e132",
  "visit_id": "dd723af9-d6ed-4bae-9ebc-7f20444b94d9",
  "camera_id": "camera-01",
  "dock_id": "dock-01",
  "stream_id": "da431683-46ed-4223-a1d6-a5f2fdf47a99",
  "track_id": 17,
  "event_type": "entered",
  "occurred_at": "2026-09-12T18:00:00+00:00",
  "plate": "ABC1D23",
  "plate_confidence": 0.92
}
```

- `201`: evento novo e permanência atualizada na mesma transação.
- `200`, `duplicate: true`: reenvio do mesmo `event_id` e conteúdo, sem nova gravação.
- `400`: contrato inválido.
- `409`: ID reutilizado com outro conteúdo, transição repetida, identidade da visita diferente ou horários incompatíveis.
- `503`: falha interna/de banco; reenviar com o mesmo `event_id`.

Consultas: `GET /dock-events/{event_id}`, `GET /dock-events?dock_id=dock-01&limit=100`,
`GET /dock-stays?dock_id=dock-01&limit=100`. O limite máximo é 500; paginação por
cursor fica para evolução. `GET /health` verifica a conexão com o PostgreSQL.

O schema é aplicado de forma idempotente no início da API. Alterações futuras no
schema precisarão de migrações versionadas. A gravação usa lock por visita e índices
únicos para impedir duplicação de início/fim, inclusive sob requisições concorrentes.

## Entrega sem broker

O worker grava cada evento na outbox SQLite em um volume antes de tentar HTTP.
Um thread separado envia em ordem, com timeout e espera crescente até 60 segundos.
Erros de rede, `408`, `429` e `5xx` são tentados novamente com o mesmo ID.
Outros `4xx` ficam na tabela com `state='rejected'` e geram log; não são descartados.
Eventos entregues são removidos da outbox; permanecem no PostgreSQL.

Inspecionar a fila:

```powershell
docker compose exec vision python -c "import sqlite3; c=sqlite3.connect('/data/outbox.sqlite3'); print(c.execute('select state,count(*) from outbox group by state').fetchall())"
```

Após corrigir a causa de uma rejeição, é possível reencaminhar o evento específico
alterando seu estado para `pending` e `next_attempt` para `0` no SQLite. Não altere
o conteúdo de um evento que já foi aceito pela API.

## Conectar uma câmera da rede ou vídeo

1. Edite `.env`: `SOURCE_MODE=video` e `VISION_BUILD_TARGET=inference`.
2. Para RTSP, configure `VIDEO_SOURCE` no `.env`. Para vídeo local, coloque o arquivo
   em `data/videos/doca.mp4` e use `VIDEO_SOURCE=/videos/doca.mp4`.
3. Ajuste `config/zone.json` à doca: pontos `[x/largura, y/altura]`, em ordem, formando
   um polígono simples sem cruzamento de arestas.
4. Mantenha `OCR_ENABLED=false` enquanto valida entrada e saída.
5. Execute `docker compose up --build -d`.
6. Para OCR, forneça `models/plate.pt` e habilite `OCR_ENABLED=true`.

Exemplo de configuração RTSP no `.env` local, substituindo os placeholders:

```dotenv
SOURCE_MODE=video
VISION_BUILD_TARGET=inference
VIDEO_SOURCE='rtsp://usuario:senha@camera.local:554/cam/realmonitor?channel=1&subtype=1'
OCR_ENABLED=false
```

Use a URL sem escapes Markdown (`rtsp://`, não `rtsp\://`). Codifique caracteres
reservados do usuário/senha, por exemplo `@` como `%40`, conforme o equipamento.
Preserve seu `.env` existente; o worker recebe a configuração pelo Compose.

Em `docker compose logs -f vision`, a mensagem `First frame received` com
`camera_id`, `width` e `height` confirma a primeira imagem válida de cada conexão.
O processamento começa automaticamente: veículos → tracking → zona → eventos →
API/permanências, mesmo com placa desconhecida. Abrir a conexão sem receber imagem
não gera essa confirmação. Falhas de captura geram novas tentativas; uma queda
interrompe visitas com `tracking_lost`, e o retorno inicia novas visitas.

O recebimento de imagens não comprova detecção nem persistência. Siga o
[roteiro de validação RTSP](.ia/testes.md#validação-operacional-com-rtsp) para
verificar cada etapa. A rede do container precisa alcançar a câmera.

O modelo COCO detecta carros, motos, ônibus e caminhões. **Ele não detecta placas**:
é necessário fornecer pesos próprios de detector de placas, compatíveis com
Ultralytics. O PaddleOCR reconhece o recorte da placa. Os modelos são baixados no
primeiro uso quando não foram provisionados. A configuração inicial usa CPU;
GPU, múltiplos streams e agendamento ainda não estão implementados.

O consenso aceita apenas `ABC1234` e `ABC1D23`, remove espaços/hífens e exige ao
menos duas observações com confiança ≥ 0,7 por padrão. Vence a soma de confiança
das observações; a confiança publicada é a média do candidato vencedor, **não uma
probabilidade calibrada de acerto**. Não há substituição automática entre letras e
dígitos. Leituras obtidas após a entrada seguem no evento de saída/interrupção e
atualizam a placa da permanência com o consenso mais recente.

Referências dos adaptadores: [Ultralytics tracking](https://docs.ultralytics.com/modes/track/),
[PaddleOCR TextRecognition](https://paddlepaddle.github.io/PaddleOCR/v3.0.0/en/quick_start.html)
e [Npgsql](https://www.npgsql.org/doc/basic-usage.html).

## Testes

Para testar uma placa exibida no celular, use `SOURCE_MODE=ocr_test` no `.env`,
mantendo `VISION_BUILD_TARGET=inference` e a URL da câmera. Esse modo dispensa o
detector `plate.pt`, procura texto na imagem inteira e mostra a última placa e seu
horário UTC em `GET /health`, no campo `last_plate_detection`. Não cria visitas.
Veja o [passo a passo](.ia/operacao.md#testar-placa-na-tela-do-celular).

Python 3.11, sem dependências de visão, a partir de `services/vision`:

```powershell
uv run --no-project --python 3.11 python -m unittest discover -s tests -v
```

Compilar API a partir da raiz:

```powershell
dotnet build services/api/Dock.Api.csproj --configuration Release
```

Com o Compose ativo, testar integração (cria visitas com docas `test-<uuid>`):

```powershell
uv run --no-project --python 3.11 python tests/api_smoke.py -v
```

Os testes de domínio cobrem confirmação, oscilação, oclusão, perda, início dentro,
reentrada e consenso. Os testes HTTP locais cobrem persistência da outbox, retry e
rejeição. A integração verifica transações, duplicatas concorrentes, ordem invertida,
validação de contrato e cálculo de permanência.

## Limites e validação da POC

A simulação não mede a qualidade do YOLO, ByteTrack ou OCR. Quando houver um vídeo,
anote manualmente entradas/saídas e compare os eventos, começando com OCR desativado.
Teste especialmente manobras, oclusões, veículo parado, bordas e desconexões.

Trocas de ID do tracker ainda podem fragmentar visitas; não há reidentificação entre
tracks. Uma queda abrupta do worker pode deixar permanências abertas, pois estados
do tracking estão em memória; a outbox recupera apenas eventos já gravados. A POC
não transforma essas situações em saídas fictícias. Reconciliação de sessões,
retenção de dados e limite de disco da outbox ficam para a próxima etapa.

A API está publicada apenas em `127.0.0.1` no Compose e não possui autenticação nesta
POC. PostgreSQL não expõe porta no host. O processamento não envia imagens a um OCR
externo. Revisar acesso e licenças dos modelos/dependências antes de distribuir ou
expor o serviço. Broker, painel, armazenamento de imagens e Kubernetes ficam fora
desta primeira versão.

## Taxa de inferência de vídeo

No modo `video`, `PROCESS_FPS=3` seleciona aproximadamente três frames por segundo
para YOLO/ByteTrack. Descartes aparecem nos logs `pipeline_metrics`; placa/OCR,
quando habilitado, roda a cada quinto frame processado. A taxa pode ser ajustada
no `.env`. Simulação e diagnóstico `ocr_test` mantêm seus comportamentos.

A captura ainda é síncrona: reduzir inferências não garante eliminar atraso
interno da câmera. Consulte [operação](.ia/operacao.md) para timestamps, fallback
de FPS, métricas e limites desta etapa.
