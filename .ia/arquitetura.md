# Arquitetura

## Escopo e tecnologias

A POC processa uma fonte de vídeo e um polígono de doca por worker. O monorepo
contém Python 3.11 no container, API .NET 10 com Npgsql e PostgreSQL 17. O pacote
Python declara suporte a versões `>=3.11,<3.13`.

O Python é um **worker**, sem servidor FastAPI. A interface HTTP pertence à API
.NET. O OCR escolhido é PaddleOCR; EasyOCR não faz parte da implementação atual.

```mermaid
flowchart LR
    S[Simulação] --> Z[ZoneProcessor]
    C[RTSP ou arquivo] --> V[OpenCV + YOLO + ByteTrack]
    V --> Z
    V --> P[Detector de placas + PaddleOCR]
    P --> A[PlateVotes por track]
    A --> Z
    Z --> O[Outbox SQLite]
    O -->|HTTP JSON| API[API .NET]
    API --> E[(dock_events)]
    API --> D[(dock_stays)]
```

## Componentes e responsabilidades

| Componente | Responsabilidade | Fonte |
|---|---|---|
| Inicialização | Carregar zona, selecionar modo, tratar sinais e iniciar entrega | [__main__.py](../services/vision/dock_vision/__main__.py) |
| Domínio | Confirmar transições, identificar visitas e agregar placas | [domain.py](../services/vision/dock_vision/domain.py) |
| Pipeline | Capturar frames e converter detecções em observações do domínio | [pipeline.py](../services/vision/dock_vision/pipeline.py) |
| Simulação | Gerar trajetórias e leituras sintéticas sem IA | [simulation.py](../services/vision/dock_vision/simulation.py) |
| Outbox | Guardar eventos antes do envio e tentar entrega em segundo plano | [outbox.py](../services/vision/dock_vision/outbox.py) |
| API | Validar, deduplicar, persistir e consultar | [Program.cs](../services/api/Program.cs) |

## Processamento de vídeo

1. A fonte é validada antes dos imports/modelos de inferência: RTSP/RTSPS precisa
   de host e porta válida quando informada; arquivos precisam existir. A URL
   original, incluindo autenticação e query, é preservada para a conexão.
   OpenCV abre a fonte com backend FFmpeg e timeouts de 5 segundos.
2. YOLO usa `model.track(..., persist=True, tracker='bytetrack.yaml')`, confiança
   mínima de 0,25 e classes COCO 2, 3, 5 e 7: carro, moto, ônibus e caminhão.
3. O centro inferior da caixa do veículo é normalizado e enviado ao processador
   de zonas, associado ao ID do tracker.
4. Se OCR estiver habilitado, a cada quinto frame o recorte do veículo passa pelo
   detector específico de placas, com confiança mínima de 0,4, e pelo PaddleOCR.
5. A melhor leitura daquele veículo/frame alimenta o consenso. O processador
   emite eventos quando confirma uma transição ou detecta perda do track.

OCR e tracking executam no mesmo loop; apenas o envio HTTP usa outro thread.
Falhas de OCR durante a leitura são registradas sem interromper o tracking. Falhas
na inicialização dos modelos ainda podem impedir o início do worker.

RTSP usa o horário corrente. Arquivos usam o início da execução mais o índice do
frame dividido pelo FPS, com fallback de 25 FPS. Isso representa tempo do vídeo,
não a data original da gravação, nem uma medição precisa de vídeos com FPS variável.

Na desconexão, visitas ativas são interrompidas e o tracker é recriado. O worker
tenta reconectar após 3 segundos. O `stream_id` permanece durante essa execução;
novas ocupações recebem novos `visit_id`.

Leituras falsas, imagens ausentes/vazias e erros nativos de abertura/leitura são
tratados como falha de captura. O primeiro frame válido de cada conexão gera
`First frame received` com câmera e dimensões antes da inferência. Não há log por
frame nem gravação das imagens. Os logs de captura da aplicação omitem URL e
credenciais; mensagens próprias de bibliotecas nativas exigem verificação no
ambiente real.

A captura é liberada antes da espera de reconexão, que pode ser interrompida pelo
encerramento. O tracker só é recriado se haverá nova tentativa; visitas são
interrompidas uma vez mesmo com limpeza final. Os timeouts dependem do backend e
não limitam o tempo da inferência nem garantem encerramento total em 5 segundos.

## Entrega e implantação

O modo opcional `SOURCE_MODE=ocr_test`, em `dock_vision/ocr_test.py`, é um
diagnóstico de texto no frame completo para teste com celular. Um thread de
captura mantém apenas o frame mais recente e seu horário; a inferência consome
essa fila de tamanho 1, evitando acumular imagens durante OCR. Reconexões recebem
uma sessão nova, impedindo confirmação entre conexões distintas.

Após duas leituras recentes e consecutivas, o worker publica `/ocr-observations`.
A API expõe a última leitura em memória em `/health`. Esse fluxo não usa zonas,
outbox ou projeção PostgreSQL. Falha de envio gera nova tentativa na próxima
leitura confirmada, sem garantia de histórico. O fluxo normal de eventos abaixo
permanece usado por `simulation` e `video`.

O produtor grava na outbox antes de enviar. Um thread envia um evento pendente por
vez, em ordem de sequência, com timeout de 5 segundos. Falhas transitórias mantêm
o primeiro evento pendente e atrasam os seguintes. Rejeições permanentes ficam
retidas e permitem avançar para o próximo pendente.

A API grava evento e projeção na mesma transação. Reenvios podem ocorrer; a
idempotência impede duplicatas persistidas. A garantia depende de o evento já ter
sido gravado na outbox: não há transação entre o estado em memória e o SQLite.

O [Compose](../compose.yaml) usa três serviços e dois volumes persistentes:
`postgres-data` e `vision-data`. A API aguarda a saúde do banco. O worker depende
do início da API, mas tolera sua indisponibilidade por meio da outbox.

O Dockerfile Python tem estágios `simulation` e `inference`. O primeiro não instala
IA; o segundo instala o extra `vision`. A configuração inicial usa CPU. `DEVICE`
é repassado aos detectores YOLO, mas o PaddleOCR está explicitamente em CPU;
o Compose não configura acesso a GPU.


## Baseline de métricas (T01)

O módulo [metrics.py](../services/vision/dock_vision/metrics.py), dependente somente
da biblioteca padrão, recebe contadores e durações do modo `video`.
O pipeline mede conjuntamente YOLO/ByteTrack; `PlateReader` mede separadamente
detecção de placa e execução completa do OCR. Logs JSON periódicos e finais
permitem comparar chamadas, falhas, FPS observado, média e p95. Cada etapa
armazena no máximo 512 durações; média e contagem abrangem toda a janela.

A instrumentação não muda cadência de inferência, domínio, outbox ou contrato
HTTP. Simulação e diagnóstico `ocr_test` preservam seus fluxos. A semântica dos
contadores e as limitações estão em [Operação](operacao.md).
