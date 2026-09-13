# Modelo de dados

Fontes: [schema.sql](../services/api/schema.sql),
[EventStore](../services/api/Program.cs) e [outbox.py](../services/vision/dock_vision/outbox.py).

## PostgreSQL: eventos brutos

`dock_events` preserva os eventos aceitos, sem endpoint de edição/exclusão.

| Grupo | Colunas |
|---|---|
| Identidade | `event_id` (PK UUID), `visit_id`, `camera_id`, `dock_id`, `stream_id`, `track_id` |
| Fato | `event_type`, `occurred_at` (`timestamptz`) |
| OCR | `plate` (`varchar(7)`), `plate_confidence` (`double precision`) |
| Auditoria | `payload` (`jsonb`), `received_at` (`timestamptz`, padrão `now()`) |

`payload` é o contrato desserializado e serializado novamente com data UTC; não
é uma cópia byte a byte do corpo HTTP original. O banco valida tipo de evento,
track não negativo e preenchimento conjunto de placa/confiança. O formato textual
da placa é validado pela API, não por uma expressão regular no SQL.

Há índices por doca/horário e visita. Dois índices únicos parciais permitem no
máximo um início (`entered` ou `observed_inside`) e um fim (`exited` ou
`tracking_lost`) por visita.

## PostgreSQL: permanências derivadas

`dock_stays` mantém uma linha por `visit_id` (PK UUID):

| Grupo | Colunas |
|---|---|
| Origem | `camera_id`, `dock_id`, `stream_id`, `track_id` |
| Intervalo | `started_at`, `ended_at`, `start_type`, `end_type` |
| Resultado | `status`, `duration_seconds`, `plate`, `plate_confidence` |
| Atualização | `updated_at` |

Horários podem ser nulos para permitir entrega fora de ordem. O banco impede fim
anterior ao início quando ambos existem. Há índice por doca/início. Consulte as
[regras de permanência](regras-de-negocio.md) para interpretar status e duração.

Não existem tabelas de veículos, cadastro de placas, câmeras, docas ou usuários,
nem chaves estrangeiras entre as duas tabelas. A aplicação mantém a correlação
por visita e sua consistência de identidade.

## Transação de gravação

1. Abrir transação e obter lock consultivo PostgreSQL por `visit_id`.
2. Consultar `event_id`: conteúdo canônico igual retorna duplicata; diferente gera conflito.
3. Verificar identidade da visita em eventos existentes.
4. Inserir evento bruto.
5. Recalcular início/fim e placa pelos eventos daquela visita; fazer upsert da permanência.
6. Confirmar a transação. Falha em qualquer gravação reverte evento e projeção.

O schema inicial é aplicado ao iniciar a API. `IF NOT EXISTS` permite repetir a
criação, mas não substitui migrações para alterar tabelas existentes. Ainda não há
ferramenta de migração nem comando de reconstrução em lote das projeções.

## SQLite: outbox do worker

| Coluna | Uso |
|---|---|
| `sequence` | PK incremental, ordem de entrega |
| `event_id` | Único na fila |
| `payload` | JSON que será reenviado sem gerar novo ID |
| `state` | `pending` ou `rejected` persistidos |
| `attempts` | Tentativas com falha |
| `next_attempt` | Horário Unix da próxima tentativa |
| `last_error` | Código HTTP ou classe do erro |

SQLite usa WAL. Após resposta `2xx`, a linha é removida; `delivered` é um estado
temporário no código, não um histórico mantido na tabela. A fila recupera eventos
gravados após reinício, mas não recupera o estado em memória do tracking.

Não há retenção automática de eventos no PostgreSQL, limite de disco da fila,
backup automatizado ou armazenamento de imagens implementados.

