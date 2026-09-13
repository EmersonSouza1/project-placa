# Contrato da API

Implementação: [Program.cs](../services/api/Program.cs). A API local do Compose
fica em `http://localhost:5080`, com porta configurável por `API_PORT`.

## Publicar evento

`POST /dock-events`, com `Content-Type: application/json`. O servidor configura
limite de corpo de 16 KiB. Todos os campos do contrato são obrigatórios; os dois
campos de placa aceitam `null` juntos. Propriedades desconhecidas são rejeitadas.

| Campo | Tipo | Regra |
|---|---|---|
| `event_id` | UUID | Não vazio; identidade do evento e chave de idempotência |
| `visit_id` | UUID | Não vazio; correlação da ocupação |
| `camera_id` | string | Não vazia/branca, até 80 caracteres |
| `dock_id` | string | Não vazia/branca, até 80 caracteres |
| `stream_id` | UUID | Não vazio; execução do worker |
| `track_id` | inteiro de 64 bits | Maior ou igual a zero |
| `event_type` | string | `entered`, `observed_inside`, `exited`, `tracking_lost` |
| `occurred_at` | data/hora | Enviar ISO 8601 com UTC/offset; armazenada em UTC |
| `plate` | string ou null | Formato brasileiro já normalizado, com sete caracteres |
| `plate_confidence` | número ou null | Finito entre 0 e 1; preenchido somente com placa |

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

A API valida a placa já normalizada; não executa OCR nem converte letras para
maiúsculas. A normalização do timestamp ocorre antes da comparação de payloads.

## Respostas e idempotência

| Código | Significado |
|---|---|
| `201` | Novo evento e projeção gravados; `Location: /dock-events/{event_id}` |
| `200` | Mesmo ID e conteúdo já aceitos; nenhuma gravação adicional |
| `400` | Contrato ou valores inválidos |
| `409` | Conteúdo diferente para ID existente, identidade inconsistente, início/fim repetido ou cronologia incompatível |
| `503` | Falha interna tratada durante a requisição; tentar novamente com o mesmo ID |

Exemplo de corpo aceito:

```json
{"event_id":"976925f7-f20e-41f9-b7b4-d7720332e132","duplicate":false}
```

O reenvio retorna `duplicate:true`. Novo `event_id` com a mesma transição de uma
visita não é reenvio idempotente: é conflito. Erros de negócio retornam `error`;
erros de parsing/limites do servidor podem ter outro formato de corpo.

## Consultas

| Endpoint | Retorno |
|---|---|
| `GET /health` | `status: "ok"` após consultar o banco e `last_plate_detection` (objeto ou null); não garante câmera ativa |
| `GET /dock-events/{event_id}` | Payload canônico do evento; `404` se ausente |
| `GET /dock-events?dock_id=dock-01&limit=100` | Array de registros brutos, incluindo `payload` e `received_at` |
| `GET /dock-stays?dock_id=dock-01&limit=100` | Array de permanências derivadas |

`dock_id` é opcional e usa igualdade exata. `limit` é inteiro opcional, padrão 100,
ajustado ao intervalo de 1 a 500. Não há paginação por cursor, filtro de período,
endpoint de upload de imagem ou documentação OpenAPI configurada nesta versão.

Eventos são selecionados por `occurred_at` descendente e ID; permanências por
`updated_at` descendente e ID. Não use a posição no array como identidade.
Os campos persistidos estão descritos em [modelo-de-dados.md](modelo-de-dados.md).

O contrato ainda não possui versionamento por URL. Mudanças incompatíveis exigem
planejar a atualização conjunta do produtor, consumidor e eventos na outbox.

## Diagnóstico OCR no health

`POST /ocr-observations` recebe JSON com todos os campos obrigatórios:
`camera_id` (1–80 caracteres, não branco), `plate` (formato brasileiro normalizado),
`confidence` (finito, entre 0,7 e 1) e `detected_at` (ISO 8601 com offset, não nulo
nem mais de um minuto no futuro). Campos desconhecidos são rejeitados. Retorna
`204` para uma observação válida e `400` para conteúdo inválido.

A API mantém somente a observação de maior `detected_at`, em memória e com horário
normalizado para UTC. Reenvios e observações antigas não substituem a mais recente.
Não grava evento, visita ou tabela; o valor é limpo ao reiniciar a API. O modo
`ocr_test` publica esse diagnóstico sem usar o contrato de eventos da doca.

Exemplo ilustrativo de `GET /health` após uma leitura:

```json
{
  "status": "ok",
  "last_plate_detection": {
    "camera_id": "camera-01",
    "plate": "ABC1D23",
    "confidence": 0.95,
    "detected_at": "2026-09-12T23:00:00+00:00"
  }
}
```

Antes da primeira leitura o campo é `null`. Ao retirar a placa, a última leitura
permanece com seu horário original; não indica presença atual nem câmera saudável.
O horário corresponde ao recebimento do frame pelo worker, não ao fim da inferência
nem ao relógio interno da câmera. A rota precisa ser consultada novamente para
ver novas leituras. Ela continua verificando o banco antes de responder `ok`.
