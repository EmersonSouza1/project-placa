# Operação e configuração

## Subir a simulação

Requer Docker com Compose e suporte a containers Linux. Execute na raiz, criando
o `.env` somente se ainda não existir, para preservar configurações locais:

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

Com zona padrão e banco inicialmente vazio, a simulação produz quatro eventos e
duas permanências: uma completa de 6 segundos e outra interrompida. A placa
`ABC1D23` é sintética. O processo permanece ativo para entregar pendências.

`docker compose restart vision` executa outra simulação com novos IDs e acumula
dados. `docker compose down` para os serviços preservando volumes; não acrescente
`-v` quando quiser manter banco e fila.

## Variáveis do .env

Fonte: [.env.example](../.env.example) e [compose.yaml](../compose.yaml).

| Variável | Padrão do exemplo | Finalidade |
|---|---|---|
| `POSTGRES_PASSWORD` | Placeholder local | Senha usada na criação do banco e conexão da API |
| `API_PORT` | `5080` | Porta local da API |
| `SOURCE_MODE` | `simulation` | `simulation`, `video` ou `ocr_test` |
| `VISION_BUILD_TARGET` | `simulation` | Estágio Docker; usar `inference` para vídeo |
| `VIDEO_SOURCE` | URL RTSP fictícia | RTSP/RTSPS ou caminho de arquivo no container |
| `CAMERA_ID` | `camera-01` | Identificador da câmera |
| `DOCK_ID` | `dock-01` | Identificador da doca |
| `ZONE_PATH` | `/config/zone.json` | Arquivo de zona no container |
| `VEHICLE_MODEL` | `yolo11n.pt` | Pesos do detector de veículos |
| `OCR_ENABLED` | `false` | Ativação do detector de placa e OCR |
| `PLATE_MODEL` | `/models/plate.pt` | Pesos específicos de detecção de placas |
| `DEVICE` | `cpu` | Dispositivo dos detectores YOLO |

O Compose define diretamente `EVENTS_URL=http://api:8080/dock-events`,
`OUTBOX_PATH=/data/outbox.sqlite3`, `YOLO_CONFIG_DIR=/data/ultralytics` e
`PADDLE_PDX_CACHE_HOME=/data/paddlex`. Também define
`ConnectionStrings__Database` e `ASPNETCORE_URLS` para a API. Adicionar essas
variáveis apenas ao `.env` não substitui valores literais do Compose.

O worker não lê `.env` por conta própria; o Compose injeta as variáveis. Na execução
local, exporte-as no shell. Os caminhos relativos padrão do worker assumem o
diretório de trabalho `services/vision`.

Alterar a senha no `.env` não altera automaticamente a senha de um usuário em um
volume PostgreSQL já inicializado. Planeje essa alteração preservando os dados.

## Configuração da zona

[config/zone.json](../config/zone.json) define:

| Campo | Padrão |
|---|---|
| `polygon` | `[[0.3,0.3],[0.8,0.3],[0.8,0.9],[0.3,0.9]]` |
| `confirmation_seconds` | `1.0` |
| `lost_after_seconds` | `5.0` |
| `minimum_plate_observations` | `2` |
| `minimum_plate_confidence` | `0.7` |

O polígono deve representar a doca real em coordenadas normalizadas. Mudanças no
arquivo exigem reiniciar o worker; não há recarga automática nem editor visual.
As trajetórias sintéticas foram feitas para a zona padrão.

## Habilitar vídeo e OCR

1. Configure `SOURCE_MODE=video` e `VISION_BUILD_TARGET=inference`.
2. Coloque um vídeo em `data/videos/doca.mp4` e use `/videos/doca.mp4`, ou configure
   a URL RTSP no `.env` local.
3. Ajuste a zona e mantenha OCR desabilitado para validar movimentações primeiro.
4. Execute `docker compose up --build -d`.
5. Depois, forneça `models/plate.pt` e habilite OCR. Pesos COCO de veículos não
   substituem um detector treinado para placas.

Pesos e dependências podem exigir downloads. O modelo de reconhecimento usado é
`en_PP-OCRv4_mobile_rec`; o PaddleOCR usa CPU. Não há preparação de GPU no Compose.

### Fonte RTSP autenticada

Preserve o `.env` existente e substitua apenas os valores necessários. Exemplo
com placeholders, para um equipamento que use esse caminho de stream:

```dotenv
SOURCE_MODE=video
VISION_BUILD_TARGET=inference
VIDEO_SOURCE='rtsp://usuario:senha@camera.local:554/cam/realmonitor?channel=1&subtype=1'
OCR_ENABLED=false
```

Use `rtsp://` ou `rtsps://` sem barras de escape de Markdown. Preserve o caminho
e os parâmetros exigidos pela câmera, incluindo `channel` e `subtype`. Codifique
caracteres reservados apenas nos componentes de usuário/senha, por exemplo `@`
como `%40`, `#` como `%23` e `%` como `%25`; não codifique a URL inteira. Aspas
simples no `.env` mantêm o valor literal para o Compose. Nunca versione a URL real
nem compartilhe saída de configuração que exponha variáveis resolvidas.

A validação local rejeita fonte vazia, host ausente e porta inválida antes dos
modelos. Isso não valida senha, codec nem alcance da rede. O container deve ter
rota para a câmera; conseguir acesso pelo host não comprova acesso pelo container.

Após `docker compose up --build -d`, acompanhe `docker compose logs -f vision`.
`First frame received camera_id=... width=... height=...` confirma recebimento
de imagem, uma vez por conexão. `Camera unavailable` indica falha de abertura;
`Camera disconnected` indica fim/falha de leitura ou imagem inválida. Ambos
informam a câmera e a espera de 3 segundos. Não há distinção automática entre
senha incorreta, falta de rede ou incompatibilidade do stream.

Quedas interrompem visitas com `tracking_lost`; reconexões recriam tracking e
geram novas visitas quando houver confirmação de ocupação. O encerramento
interrompe a espera e libera a captura, mas pode aguardar o retorno/timeout da
chamada nativa ou da inferência. Os timeouts de abertura/leitura são de 5 segundos
e dependem do backend. Bibliotecas nativas podem produzir logs próprios: confira
essa saída antes de compartilhar diagnósticos.

Confira eventos e permanências seguindo o [roteiro RTSP](testes.md#validação-operacional-com-rtsp).
Para parar, use `docker compose stop vision`, preservando volumes. Para voltar à
simulação, restaure `SOURCE_MODE=simulation` e `VISION_BUILD_TARGET=simulation`
e reconstrua; isso produz novos eventos sintéticos. Não remova volumes.

## Diagnóstico

### Testar placa na tela do celular

No `.env` local, use `SOURCE_MODE=ocr_test`, `VISION_BUILD_TARGET=inference` e a
mesma `VIDEO_SOURCE` RTSP. Execute `docker compose up --build -d`. Nesse modo,
`OCR_ENABLED` não controla o teste: ele é próprio para OCR e dispensa `plate.pt`.
As bibliotecas são instaladas na imagem; nenhum pacote Python é exigido no host.

O PaddleOCR usa `PP-OCRv5_mobile_det` para localizar texto na imagem inteira e
`en_PP-OCRv4_mobile_rec` para reconhecer os recortes. Os modelos são baixados no
primeiro uso e ficam no volume `/data/paddlex`. O modo roda em CPU com MKL-DNN
desativado para evitar a incompatibilidade observada no Paddle 3.3.1.

Exiba uma placa brasileira, como `ABC1D23` ou `ABC1234`, grande e nítida no celular
voltado para a câmera. Evite reflexos e mantenha a tela parada por alguns segundos.
O sistema exige duas leituras consecutivas da mesma placa, em frames diferentes
da mesma conexão, separados por até 15 segundos e com confiança mínima de 0,7.
Ele normaliza espaços/hífens e maiúsculas, sem inventar substituições entre letras
e números. O teste identifica texto com formato de placa, sem comprovar placa física.

Acesse `http://localhost:5080/health` e atualize a página para ver
`last_plate_detection.plate` e `last_plate_detection.detected_at` (UTC).
O valor fica `null` até a primeira leitura confirmada. A última detecção permanece
após retirar o celular, com o horário da imagem; reiniciar a API limpa o diagnóstico.
Para acompanhar automaticamente no PowerShell:

```powershell
while ($true) {
    Invoke-RestMethod http://localhost:5080/health | ConvertTo-Json -Depth 4
    Start-Sleep -Seconds 2
}
```

Esse modo suspende o processamento de zonas e a entrega da outbox, preservando os
dados existentes. Não cria eventos nem visitas. Para retomar a doca, restaure
`SOURCE_MODE=video` e execute `docker compose up -d vision`. O OCR de veículos
continua dependendo de `OCR_ENABLED=true` e de pesos próprios em `plate.pt`.

### Diagnóstico dos serviços

| Sintoma | Verificação |
|---|---|
| API inacessível | Conferir `docker compose ps`, logs da API e saúde do PostgreSQL |
| Fonte inválida | Conferir `VIDEO_SOURCE`, host, porta e ausência de escapes Markdown |
| Nenhum `First frame received` | Conferir rota da rede do container, credenciais locais, caminho/canal, codec e estágio `inference` |
| Eventos não aparecem | Inspecionar logs do worker e a outbox; a API pode estar indisponível |
| `rejected` na outbox | Conferir contrato/identidade/cronologia; reenvio cego não corrige `409` |
| Visita interrompida | Verificar ausência de detecção, fim do arquivo e desconexões |
| Placa nula | Conferir OCR habilitado, pesos, qualidade dos recortes e consenso mínimo |
| Erro ao importar IA | Conferir se o estágio de build é `inference` |

Inspecionar contagens da outbox:

```powershell
docker compose exec vision python -c "import sqlite3; c=sqlite3.connect('/data/outbox.sqlite3'); print(c.execute('select state,count(*) from outbox group by state').fetchall())"
```

Falhas transitórias usam espera de 1, 2, 4, 8, 16, 32 e até 60 segundos. Outros
`4xx`, exceto `408` e `429`, ficam retidos como rejeitados. Após corrigir a causa,
uma intervenção específica no SQLite pode repor `state='pending'` e
`next_attempt=0`; não há endpoint administrativo para isso.

A API não possui autenticação e está publicada somente em `127.0.0.1`. PostgreSQL
não publica porta no host. Mantenha credenciais fora da documentação e considere
que bibliotecas de captura podem produzir logs próprios ao diagnosticar RTSP.


## Métricas locais do pipeline de vídeo (T01)

Em `SOURCE_MODE=video`, a mensagem de log é um objeto JSON com
`event=pipeline_metrics`, `camera_id` e `stream_id`. O formato padrão do logger
mantém seu prefixo de data/nível antes desse JSON. Para acompanhar no Compose:

```powershell
docker compose logs -f vision
```

O resumo é verificado entre iterações, aproximadamente a cada 30 segundos, e
emitido novamente na limpeza final do pipeline, inclusive após erro de inferência.
Uma captura/inferência bloqueada pode atrasar o resumo; não existe thread de
telemetria. Falhas durante a inicialização dos modelos não geram resumo final.

Cada resumo cobre o intervalo desde o anterior (o primeiro inclui a inicialização
dos modelos). Contadores e amostras reiniciam após a emissão. Os campos são:

| Campo | Significado |
|---|---|
| `frames_received` | Leituras com `ok=True`, incluindo imagem inválida |
| `frames_processed` | Frames enviados a `model.track`, incluindo chamadas que falharam |
| `frames_discarded` | Leituras bem-sucedidas descartadas por imagem inválida ou encerramento antes da inferência |
| `received_fps` / `processed_fps` | Contadores divididos pelo tempo real decorrido no intervalo |
| `interval_seconds` / `final` | Duração da janela e indicação de resumo final |
| `stages` | Estatísticas de `vehicle_tracking`, `plate_detection` e `ocr` |

Cada etapa informa `calls`, `errors`, `mean_ms`, `p95_ms` e `sample_count`.
A média abrange todas as chamadas do intervalo. O p95 usa nearest-rank:
ordena as últimas até 512 durações da etapa e seleciona a posição
`ceil(0.95 * n)`, com posição inicial 1. Portanto, em janelas com mais de
512 chamadas, o p95 representa apenas as amostras mais recentes. Sem chamadas,
média e p95 são `null`. Uma chamada que falha também entra no tempo e no contador.

A etapa `vehicle_tracking` mede a chamada YOLO/ByteTrack completa; não separa
detector e associação. OCR inclui o consumo do gerador de resultados, não apenas
sua criação. Os tempos usam relógio monotônico e não alteram horários de eventos.

Esses FPS medem leitura/processamento pela aplicação, não o FPS nativo da câmera:
o loop síncrono ainda não consegue observar descartes internos do driver/FFmpeg.
`ok=False` (inclusive fim de arquivo) não conta como frame recebido/descartado.
Esta etapa não implementa sampling, filas, métricas de CPU/memória, contagem de OCR
por visita ou instrumentação do diagnóstico `ocr_test`. Com `OCR_ENABLED=false`,
as etapas de placa/OCR continuam com zero chamadas. Não há URL, imagem ou placa
no payload das métricas.
