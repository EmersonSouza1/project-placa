# Testes e validação

## Comandos e requisitos

| Verificação | Diretório de trabalho | Comando |
|---|---|---|
| Domínio, outbox e pipeline | `services/vision` | `uv run --no-project --python 3.11 python -m unittest discover -s tests -v` |
| Compilação .NET | Raiz | `dotnet build services/api/Dock.Api.csproj --configuration Release` |
| Integração HTTP/PostgreSQL | Raiz | `uv run --no-project --python 3.11 python tests/api_smoke.py -v` |

Os testes Python usam a biblioteca padrão e não exigem modelos, GPU ou câmera.
Os do pipeline substituem captura, inferência e relógio por dublês, usando o domínio
real para verificar os eventos. Os de outbox abrem um servidor HTTP local temporário. A integração
exige a API e o PostgreSQL ativos, normalmente via Compose. `API_URL` permite
substituir o destino padrão `http://localhost:5080`.

## Cobertura existente

| Arquivo | Cenários |
|---|---|
| [test_domain.py](../services/vision/tests/test_domain.py) | Entrada/saída, reentrada, oscilação, início dentro, perda, oclusão, interrupção, identidade, zona, formatos e consenso de placas, simulação |
| [test_outbox.py](../services/vision/tests/test_outbox.py) | Persistência após recriação da outbox, sucesso, retry com mesmo evento, retenção de rejeição e `429` |
| [test_pipeline.py](../services/vision/tests/test_pipeline.py) | Validação antes de imports de IA, URL autenticada preservada, falhas nativas, frames inválidos, logs sem credenciais, primeiro frame, entrada/saída, início dentro, ausência de detecção, reconexão com ID reutilizado, encerramento, OCR opcional, tempo de mídia/FPS e seleção de modo |
| [api_smoke.py](../tests/api_smoke.py) | Visita completa, duplicata, fim antes do início, interrupção, início desconhecido, conflitos, concorrência e validação |
| [test_ocr_test.py](../services/vision/tests/test_ocr_test.py) | Formato/confiança, confirmação em frames distintos, expiração e reconexão, timestamp do frame e modo sem zonas/outbox |
| [ocr_smoke.py](../tests/ocr_smoke.py) | Snapshot OCR no health, validação e proteção contra atualização fora de ordem |

O teste `ocr_smoke.py` publica uma observação sintética de diagnóstico. Execute
antes de iniciar a captura de teste e reinicie somente a API ao terminar, para
limpar o snapshot; não apresente essa leitura como evidência da câmera.

## Evidências do modo OCR com celular

Na implementação de `SOURCE_MODE=ocr_test`, em 12/09/2026:

- 36 testes Python passaram, incluindo quatro testes novos do diagnóstico.
- `dotnet build services/api/Dock.Api.csproj --configuration Release` passou sem
  avisos ou erros.
- No Compose, passaram o teste `ocr_smoke.py` e os sete testes `api_smoke.py`.
  A API foi reiniciada após o teste para limpar a observação sintética.
- Inferência real do PaddleOCR sobre imagem sintética criada em memória com
  `ABC1D23` retornou o mesmo texto e confiança aproximada de 0,9997. Nenhuma imagem
  foi salva e essa inferência não foi publicada no health.
- Paddle 3.3.1 apresentou erro `ConvertPirAttribute2RuntimeAttribute` com a
  otimização MKL-DNN; o modo de teste usa `enable_mkldnn=False`, configuração em
  que a inferência passou. Os modelos de texto estão no volume `/data/paddlex`.
- O acerto na imagem sintética não valida a leitura de uma tela de celular na
  câmera. Enquadramento, tamanho da placa, brilho/reflexos e nitidez ainda precisam
  ser verificados no ensaio do usuário.
- Após reconstrução e ativação do container, `OCR test ready` e recebimento real
  de frames 640 × 480 foram registrados às 00:37:19 e 00:37:22 UTC de 13/09
  (21:37 de 12/09 no horário de Brasília). Serviço em execução sem reinícios;
  `/health` retornou `status=ok` e `last_plate_detection=null`, aguardando a placa.

O teste de integração cria docas `test-<uuid>` e não remove os registros ao terminar.
Use um ambiente de testes. Uma falha de banco não deve ser interpretada como
aprovação parcial do teste.

## Resultado esperado da simulação

Com configuração padrão, cada execução gera:

| Track | Sequência | Resultado |
|---|---|---|
| 1 | `entered` → `exited` | Mesma visita, placa sintética `ABC1D23`, duração 6 s |
| 2 | `observed_inside` → `tracking_lost` | Outra visita, placa nula, duração nula |

A contagem total do banco cresce a cada reinício da simulação. Asserções de
integração devem isolar os identificadores da execução em vez de assumir banco vazio.

## Evidências registradas

Na implementação inicial de **12/09/2026**:

- 18 testes Python passaram: 14 de domínio e 4 de outbox.
- A API compilou em Release sem avisos/erros e foi publicada localmente com `dotnet publish`.
- A sintaxe dos adaptadores Python e do teste de integração foi verificada com `compileall`.
- Compose/PostgreSQL não foram executados: Docker e PostgreSQL não estavam disponíveis no ambiente.
- Os sete testes de integração foram criados, mas não executados nessa validação.
- YOLO, ByteTrack, PaddleOCR e RTSP reais permanecem sem validação empírica no projeto.

Esses resultados são históricos. Atualize este registro ao executar novas etapas,
informando ambiente, comandos, resultado e limitações.

Na aplicação de `consolidate-rtsp-camera-processing`, em **12/09/2026**:

- Windows/PowerShell, Python 3.11 gerenciado pelo `uv`: **32 testes passaram**
  com o comando da tabela, incluindo 14 testes novos de pipeline/inicialização.
- O sandbox bloqueou a leitura da instalação Python e o cache padrão; a execução
  autorizada fora do sandbox concluiu a suíte em aproximadamente 2,2 segundos.
- Docker não foi encontrado no PATH nem no caminho padrão de Docker Desktop;
  OpenCV e Ultralytics não estão instalados no Python inspecionado. A pasta
  `models` contém apenas documentação e placeholder, sem pesos.
- Não há serviço escutando em `127.0.0.1:5080`. Integração API/PostgreSQL e ensaio
  de recuperação da API com eventos reais não foram executados.
- Câmera real, YOLO, ByteTrack e OCR continuam sem validação empírica. A URL real
  não foi gravada e a configuração local não foi alterada. Testes com dublês não
  medem qualidade de detecção, tracking ou reconhecimento.

## Validação operacional com RTSP

### Execução em containers em 12/09/2026

Após a verificação anterior, o Docker Desktop foi localizado no perfil do usuário
fora do sandbox, com motor Linux ativo. A ausência de pacotes de inferência no
Python do host não impede a execução em containers.

- `docker compose up --build -d` concluiu: PostgreSQL saudável, API e visão em
  execução, sem reinícios na checagem inicial.
- Docker Desktop 4.86.0, Engine 29.7.2, Compose 5.3.1; imagem de visão com Python
  3.11, OpenCV efetivo 4.10.0 e Ultralytics 8.4.150.
- Configuração local em modo `video`, estágio `inference`, CPU e OCR desligado;
  pesos `yolo11n.pt` baixados automaticamente no primeiro uso.
- Captura real confirmada pelo log `First frame received`, câmera `camera-01`,
  **640 × 480**, às **23:40:51 UTC**. A URL está somente no `.env` local ignorado.
- `GET /health` retornou `status=ok`. Os **7 testes de integração passaram**
  dentro do container, contra API/PostgreSQL da rede Compose, com o comando abaixo.
  Foram criadas visitas isoladas em docas `test-<uuid>`.
- Outbox sem pendências na checagem inicial. A biblioteca Ultralytics informou
  fallback de configurações para `/tmp/Ultralytics`; isso não impediu a captura.
- O polígono continua sendo o padrão de `config/zone.json`, sem calibração visual
  da doca. Entrada/saída anotada, precisão de tracking, queda/retorno da câmera e
  indisponibilidade da API com eventos reais permanecem pendentes. Captura real
  e testes de contrato não comprovam essas etapas nem reconhecimento de placas.

Na raiz, em PowerShell, usando o Python já instalado no container:

```powershell
Get-Content tests/api_smoke.py -Raw -Encoding UTF8 | docker compose exec -T -e API_URL=http://api:8080 vision python - -v
```

### Roteiro de aceitação

Use um ambiente de testes com Docker/Compose, acesso à rede da câmera, pesos de
veículos e API/PostgreSQL ativos. Prepare a [configuração RTSP](operacao.md#fonte-rtsp-autenticada)
com OCR desligado e zona ajustada ao enquadramento. Use as evidências acima para
distinguir captura já verificada dos ensaios ainda pendentes; registre os
impedimentos quando não puder executá-los.

1. **Captura:** execute `docker compose up --build -d` e acompanhe
   `docker compose logs -f vision`. Registre `camera_id`, horário e dimensões de
   `First frame received`. Conexão aberta sem imagem não atende esse critério.
   Verifique localmente se mensagens nativas expõem a fonte antes de compartilhar logs.
2. **Movimentação:** anote manualmente um veículo confirmado fora, entrando e
   saindo da zona. Compare com `entered`/`exited` de uma mesma visita e placa nula.
   O intervalo entre confirmações deve corresponder à permanência projetada;
   registre diferenças em relação à anotação, eventos falsos ou ausentes e trocas de ID.
3. **Início dentro:** inicie a observação com veículo já dentro e confirme
   `observed_inside`, sem afirmar entrada nem duração total conhecida.
4. **Queda/retorno:** em ambiente controlado, interrompa o acesso ao stream durante
   uma visita e restaure-o. Verifique um `tracking_lost` para a visita anterior,
   nenhuma saída fictícia, outro log de primeiro frame e nova visita com
   `observed_inside` se o veículo permanecer dentro. O `stream_id` deve permanecer
   o mesmo enquanto o worker não reiniciar.
5. **Persistência:** consulte os endpoints abaixo e correlacione por `event_id`
   e `visit_id`, filtrando a doca do ensaio. API saudável sozinha não comprova
   captura; primeiro frame sozinho não comprova eventos gravados.

```powershell
Invoke-RestMethod http://localhost:5080/health
Invoke-RestMethod 'http://localhost:5080/dock-events?dock_id=dock-01&limit=100'
Invoke-RestMethod 'http://localhost:5080/dock-stays?dock_id=dock-01&limit=100'
uv run --no-project --python 3.11 python tests/api_smoke.py -v
```

6. **Entrega após indisponibilidade:** apenas no ambiente de testes, execute
   `docker compose stop api`, observe uma movimentação e inspecione contagens da
   outbox conforme o guia de operação. Registre os IDs pendentes localmente;
   execute `docker compose start api`, aguarde os retries e confirme os mesmos IDs
   persistidos uma vez, sem pendências daquele ensaio. Não remova volumes nem eventos.
7. **Registro:** anote data, hardware, versões, modelos/pesos, zona, dimensões,
   intervalo observado, resultados por etapa e limitações. Não inclua URL, senha
   ou imagens no versionamento. Registre precisão de detecção separadamente de
   correção do transporte e da persistência. OCR real requer ensaio adicional
   com detector de placas treinado; leituras controladas não o substituem.

Os timeouts configurados de 5 segundos dependem do backend e não limitam a
inferência. Confirme encerramento e recuperação no equipamento real, sem assumir
SLA para o processo inteiro. Uma cena sem veículos comprova somente a captura.

## Validação futura com vídeo real

1. Obter um vídeo da doca e anotar manualmente veículos, entradas e saídas.
2. Configurar polígono e rodar com OCR desabilitado.
3. Comparar eventos com a anotação, incluindo manobras, bordas, veículo parado,
   oclusões e múltiplos veículos visíveis.
4. Medir eventos falsos/ausentes, fragmentação de IDs e diferença temporal das
   confirmações; testar desconexão e recuperação.
5. Habilitar detector de placas e OCR e medir acerto do consenso por visita.
6. Registrar hardware, versões, pesos, zona, FPS e resultados para reprodução.

Ainda não há metas numéricas de aceitação acordadas. Defina-as com os responsáveis
pela operação antes de declarar a POC validada. Simulação aprovada não mede
precisão de detecção, estabilidade de tracking ou acurácia do OCR.


## Evidência T01 — Baseline de métricas, 13/09/2026

No Windows/PowerShell, a partir de `services/vision`, foi executado:

```powershell
uv run --no-project --python 3.11 python -m unittest discover -s tests -v
```

Resultado: **46 testes passaram** em aproximadamente 2,2 segundos, incluindo
10 novos testes. `test_metrics.py` cobre periodicidade, reset da janela, FPS,
média, p95 nearest-rank, limite de memória, validação de parâmetros, falhas e
temporização do gerador de OCR. `test_pipeline.py` também verifica contagem de
frames inválidos/processados, OCR desabilitado e resumo final em erro de YOLO.
Os testes existentes de domínio, simulação, outbox, reconexão e diagnóstico
continuam passando sem bibliotecas de inferência.

Não foram executados benchmark, câmera/modelos reais ou integração .NET/PostgreSQL
nesta mudança. Os testes usam relógios/inferências substituídos e não demonstram
ganho de desempenho ou precisão. Contrato HTTP, API e persistência não mudaram.

## Evidência T02 — Frame sampling, 13/09/2026

Executado em Windows/PowerShell, no diretório `services/vision`:

```powershell
uv run --no-project --python 3.11 python -m unittest discover -s tests -v
```

**58 testes passaram**, incluindo 12 novos. Os cenários cobrem seleção a partir
de 25/30/60 FPS, taxa configurada, fonte lenta, ausência de compensação após pausa,
validação antes de imports de inferência, FPS inválido/incorreto, posição de mídia
repetida/regressiva/ausente, reconexão e independência entre seleção RTSP e relógio
de parede. Um vídeo sintético de 210 frames a 30 FPS envia 21 frames ao detector,
descarta 189 e preserva entrada/saída em 103/106 s, mesma visita e OCR posterior.

Na raiz, `docker compose --env-file .env.example config --quiet` passou. Nenhum
container foi iniciado ou reconfigurado. A validação usa placeholders.

Sem ensaio de câmera, modelos reais ou benchmark; testes com dublês não validam
precisão do tracking em baixa cadência nem ausência de backlog. API/contrato e
persistência não foram alterados.

## Evidência T03 — Fila limitada, 13/09/2026

Executado no Windows/PowerShell, a partir de `services/vision`:

```powershell
uv run --no-project --python 3.11 python -m unittest discover -s tests -v
```

**72 testes passaram** em aproximadamente 2,3 segundos. Os 14 novos testes
cobrem capacidade/configuração, saturação e descarte, FIFO para arquivos, captura
durante inferência bloqueada, timestamp/sessão originais, reconexão, métricas entre
janelas, erros sanitizados e shutdown em fila cheia ou leitura em andamento.

Os testes concorrentes usam threads reais com eventos de sincronização e captura/
inferência substituídas. No cenário de sobrecarga integrado, 21 frames chegam,
2 são processados e 19 descartados; a fila não excede 5 e os timestamps entregues
são 101 e 121. Outro cenário verifica nova visita após reconexão, mesmo `stream_id`
e tracker recriado. Testes antigos de semântica RTSP usam leitura passo a passo
para não depender do escalonamento; arquivos e os cenários concorrentes usam o
leitor com thread real.

Na raiz, `docker compose --env-file .env.example config --quiet` passou. Nenhum
container foi iniciado/reconfigurado e o `.env` real não foi alterado.

Sem câmera/modelos reais, benchmark, medição de memória do processo ou integração
.NET/PostgreSQL nesta mudança. A fila é limitada por construção e por testes;
isso não comprova latência, precisão de tracking ou limites dos buffers nativos.


Na implementação da **T04**, em **13/09/2026**, foram adicionados testes unitários da configuração normalizada, limites, recorte e translação das caixas para o frame completo. Eles não exigem OpenCV, câmera ou modelos. A inferência real com ROI ainda precisa ser comparada no benchmark T10; testes sintéticos não comprovam redução de CPU nem qualidade de detecção.
