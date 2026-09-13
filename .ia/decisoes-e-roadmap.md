# Decisões e roadmap

Registro inicial: **12/09/2026**. As decisões abaixo descrevem a POC implementada;
as etapas de evolução são propostas, sem prazo ou compromisso de entrega.

## Decisões atuais

| Decisão | Motivo | Consequência |
|---|---|---|
| Monorepo e Docker Compose | Facilitar desenvolvimento conjunto e execução da POC | Três serviços no mesmo projeto |
| Python para vídeo, .NET para API | Separar inferência e persistência/integração | Contrato JSON precisa evoluir nos dois lados |
| Uma fonte e uma zona por worker | Validar primeiro a lógica da doca | Sem distribuição de streams nesta etapa |
| Simulação por padrão | Começar sem câmera e sem pesos disponíveis | Não comprova qualidade dos modelos |
| YOLO + ByteTrack | Detectar veículos e manter associação entre frames | Trocas de ID ainda podem fragmentar visitas |
| Detector próprio de placa + PaddleOCR | Separar localização e leitura da placa | É necessário fornecer pesos de detecção de placas |
| OCR opcional | Movimentação não deve depender de leitura perfeita | Placa pode permanecer nula |
| HTTP + outbox SQLite, sem broker | Entrega persistente com poucos componentes | Retentativas e rejeições ficam sob responsabilidade do worker |
| Evento bruto + permanência derivada | Preservar fatos e facilitar consultas | Projeção precisa permanecer transacional e idempotente |
| Estados explícitos de incerteza | Não inventar entrada/saída em perda de observação | Algumas visitas ficam sem duração completa |

## Limitações conhecidas

- Tracking e votos estão em memória; queda abrupta pode deixar visitas abertas.
- A outbox só protege eventos já gravados; não há atomicidade entre transição de
  estado e inserção no SQLite.
- Não há reidentificação entre tracks ou câmeras, nem reconciliação automática de
  permanências abertas após falha.
- OCR executa no loop de vídeo e pode reduzir a taxa de processamento.
- A projeção só recebe nova placa quando há novo evento; não há atualização
  periódica da placa em visita aberta.
- Não há autenticação, painel, evidências em imagem, métricas centralizadas,
  paginação por cursor, política de retenção ou limite de disco da outbox.
- Não há migrations versionadas, backup automatizado ou pipeline de CI configurado.
- Dependências Python usam faixas de versão sem lockfile; a imagem de inferência
  ainda precisa ter instalação e compatibilidade verificadas em execução real.
- O servidor consegue consultar PostgreSQL no `/health`, mas isso não comprova
  saúde da câmera, entrega da fila ou qualidade de reconhecimento.

## Evolução proposta

| Etapa | Trabalho | Evidência necessária |
|---|---|---|
| 1 — Integração da simulação | Subir Compose e executar os testes HTTP/PostgreSQL | Idempotência, concorrência, ordem invertida e permanência corretas |
| 2 — Tracking real | Obter vídeo, calibrar zona e observar eventos sem OCR | Comparação com entradas/saídas anotadas manualmente |
| 3 — OCR real | Fornecer detector de placas, validar recortes e consenso | Acerto por visita medido em amostra representativa |
| 4 — Robustez operacional | Reconciliar falhas, controlar armazenamento, adicionar acesso e observabilidade conforme ambiente | Recuperação e operação previsíveis |
| 5 — Escala | Paralelizar streams e planejar uso/agendamento de GPU | Medições de CPU/GPU, latência e capacidade |

Adicionar mensageria somente quando volume, desacoplamento ou recuperação
justificarem o custo operacional. Kubernetes, gateways por unidade, armazenamento
de imagens e integrações WMS/TMS/ERP são possibilidades de expansão, não componentes
presentes na POC.

## Informações ainda necessárias

- Vídeo/câmera de teste e posicionamento real da doca.
- Pesos do detector de placas e condições de uso desses pesos.
- Hardware disponível e demanda futura de streams.
- Metas aceitáveis para perda de eventos, falsos eventos, precisão e latência.
- Requisitos de retenção, autenticação, auditoria e integração operacional.

Não registrar credenciais ou dados sensíveis ao preencher essas informações.
