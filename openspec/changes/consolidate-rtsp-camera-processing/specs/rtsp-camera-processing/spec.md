## Purpose

Permitir que uma câmera de rede forneça imagens continuamente ao monitoramento da doca, com diagnóstico da captura, recuperação de conexão e preservação do significado dos eventos.

## ADDED Requirements

### Requirement: Configuração explícita da fonte de rede

O sistema MUST aceitar uma URL RTSP/RTSPS em `VIDEO_SOURCE` no modo `video`, incluindo autenticação e parâmetros de canal, preservando o valor utilizado na conexão. Configuração ausente ou URL sem host ou com porta inválida MUST falhar antes de carregar modelos, com mensagem sem credenciais. A simulação MUST permanecer como modo padrão e arquivos locais MUST continuar suportados.

#### Scenario: Câmera autenticada configurada
- **WHEN** o operador configura `SOURCE_MODE=video`, `VISION_BUILD_TARGET=inference` e `VIDEO_SOURCE=rtsp://usuario:senha@camera.local:554/cam/realmonitor?channel=1&subtype=1`
- **THEN** o sistema tenta capturar imagens dessa fonte preservando autenticação, caminho e query

#### Scenario: Configuração inválida
- **WHEN** o modo é `video` e a fonte está vazia ou a URL RTSP não tem host ou possui porta inválida
- **THEN** o sistema informa erro de configuração antes da inicialização dos modelos, sem imprimir a fonte ou credenciais

#### Scenario: Simulação independente
- **WHEN** o operador inicia a configuração padrão
- **THEN** a simulação funciona sem acessar a câmera e sem importar dependências de inferência

#### Scenario: Arquivo local
- **WHEN** a fonte é um arquivo de vídeo existente e alcança seu fim
- **THEN** o sistema encerra a captura sem reproduzir o arquivo automaticamente e mantém a entrega de eventos pendentes ativa

### Requirement: Evidência de captura e frames válidos

O sistema MUST informar nos logs da aplicação o primeiro frame válido recebido em cada conexão, identificando a câmera e as dimensões da imagem. Abrir a conexão sem receber imagem MUST NOT ser apresentado como captura confirmada. Frames ausentes ou vazios MUST NOT ser enviados ao processamento. Logs da aplicação MUST omitir a URL completa, usuário e senha da fonte.

#### Scenario: Primeiro frame recebido
- **WHEN** uma conexão fornece seu primeiro frame válido
- **THEN** o sistema registra câmera e dimensões uma vez nessa conexão e encaminha a imagem para processamento

#### Scenario: Conexão sem imagem
- **WHEN** a conexão abre mas a primeira leitura falha ou retorna imagem vazia
- **THEN** o sistema registra indisponibilidade, não confirma recebimento e inicia recuperação sem executar inferência sobre esse resultado

#### Scenario: Diagnóstico com autenticação
- **WHEN** uma tentativa de conexão autenticada falha
- **THEN** os logs gerados pela aplicação identificam a câmera e a tentativa de recuperação sem incluir URL, usuário ou senha

### Requirement: Processamento automático e eventos existentes

O sistema MUST processar frames válidos para detectar e rastrear veículos, avaliar a zona configurada e entregar os eventos à fila persistente existente. OCR MUST ser opcional; placa desconhecida MUST permitir visitas. Os eventos MUST preservar o contrato HTTP e as identidades por `event_id` e `visit_id`.

#### Scenario: Entrada e saída observadas sem OCR
- **WHEN** um veículo é confirmado fora, depois dentro e depois fora da zona com OCR desabilitado
- **THEN** são gerados `entered` e `exited` com o mesmo `visit_id`, IDs de evento distintos e placa nula, permitindo projetar a permanência pelo intervalo entre confirmações

#### Scenario: Primeira observação dentro
- **WHEN** um veículo é confirmado dentro sem observação anterior confirmada fora
- **THEN** é gerado `observed_inside`, e não `entered`, com duração total desconhecida

#### Scenario: API temporariamente indisponível
- **WHEN** uma movimentação gera evento e a API está indisponível
- **THEN** o evento permanece na fila persistente e é reenviado com o mesmo ID e conteúdo quando a API retornar

#### Scenario: OCR habilitado
- **WHEN** OCR está habilitado, os modelos necessários estão disponíveis e leituras satisfazem o consenso configurado
- **THEN** a placa pode enriquecer os eventos subsequentes conforme as regras existentes, sem reescrever eventos anteriores

### Requirement: Recuperação e encerramento da captura

O sistema MUST configurar limites de 5 segundos para abertura e leitura da captura e repetir tentativas RTSP após espera de 3 segundos interrompível por encerramento. Uma falha de leitura ou frame inválido MUST liberar a captura e interromper visitas ativas uma única vez com `tracking_lost`. A reconexão MUST iniciar tracking sem estado anterior e novas ocupações MUST receber novos `visit_id`, mesmo quando o ID numérico do track se repetir.

#### Scenario: Câmera indisponível na inicialização
- **WHEN** a câmera não fornece conexão utilizável
- **THEN** o sistema registra indisponibilidade e tenta novamente após a espera, sem inventar eventos de movimentação

#### Scenario: Queda durante uma visita
- **WHEN** a leitura do stream falha durante uma visita ativa
- **THEN** o sistema enfileira um único `tracking_lost` para essa visita, libera a conexão e tenta reconectar sem gerar `exited`

#### Scenario: Retorno com veículo dentro
- **WHEN** a câmera volta após interrupção e um veículo é confirmado dentro, inclusive com o mesmo ID numérico anterior
- **THEN** o sistema gera `observed_inside` com novo `visit_id`, mantendo o `stream_id` da execução do worker

#### Scenario: Encerramento solicitado
- **WHEN** o processo recebe solicitação de encerramento durante captura ou espera de reconexão
- **THEN** o sistema para novas tentativas, libera a captura e enfileira interrupções pendentes sem duplicá-las, respeitando o retorno ou timeout da chamada de captura em andamento
