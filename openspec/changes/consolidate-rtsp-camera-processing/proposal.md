## Why

A operação precisa consumir imagens de uma câmera da rede e executar automaticamente o monitoramento da doca. O pipeline já implementa captura RTSP, tracking e eventos, mas não possui testes do adaptador nem confirmação explícita de frames recebidos, e ainda não foi validado com câmera real.

## What Changes

- Consolidar a configuração de uma câmera RTSP autenticada via `VIDEO_SOURCE`, com `SOURCE_MODE=video` e estágio `inference`, preservando a simulação padrão.
- Validar a configuração antes da inferência e informar recebimento do primeiro frame de cada conexão, indisponibilidade e reconexão, sem expor a URL ou credenciais nos logs da aplicação.
- Garantir que somente frames válidos alimentem YOLO, ByteTrack, zonas e OCR opcional, produzindo eventos pela outbox existente.
- Cobrir falhas de abertura, interrupção de leitura, reconexão e encerramento com testes sem dependências de inferência.
- Documentar configuração e aceitação ponta a ponta com câmera real, distinguindo captura, detecção e persistência.

## Capabilities

### New Capabilities

- `rtsp-camera-processing`: contrato de configuração, captura contínua, processamento e recuperação de uma câmera de rede. É uma nova especificação de um suporte parcialmente existente; não há specs principais no projeto.

### Modified Capabilities

Nenhuma.

## Impact

Alterações previstas no pipeline e na inicialização Python, testes de visão, `.env.example`, README e documentação `.ia` de arquitetura, operação e testes. O Compose já encaminha as variáveis necessárias e mantém o estágio de inferência separado. Não se prevê alteração de API, payloads, tabelas ou dependências pesadas.

As ações consideradas são as atuais: detectar/rastrear veículos, confirmar entrada/saída na zona, registrar permanência e reconhecer placas quando habilitado. Painel, gravação de imagens, controle físico da câmera e múltiplas câmeras ficam fora do escopo. A câmera real, sua rede e os pesos são pré-requisitos da validação operacional; a proposta não comprova seu funcionamento.
