# Guia para trabalhar neste repositório

## Contexto e objetivo

Este monorepo implementa uma POC de monitoramento de **uma câmera / uma doca**.
O serviço Python acompanha veículos e produz eventos; a API .NET recebe esses
eventos e grava o histórico e a permanência no PostgreSQL.

A prioridade é validar **tracking + zonas + entrada/saída**, mesmo sem reconhecer
a placa. O modo padrão é a simulação de trajetórias. A arquitetura atual usa
HTTP e outbox SQLite; não há broker.

## Documentação de referência

Leia este guia e os documentos relevantes à mudança. O índice está em
[.ia/README.md](.ia/README.md).

| Assunto | Documento |
|---|---|
| Componentes e fluxo de processamento | [.ia/arquitetura.md](.ia/arquitetura.md) |
| Zonas, estados, permanência e OCR | [.ia/regras-de-negocio.md](.ia/regras-de-negocio.md) |
| Endpoints, payloads e idempotência | [.ia/contrato-api.md](.ia/contrato-api.md) |
| Tabelas, índices e persistência | [.ia/modelo-de-dados.md](.ia/modelo-de-dados.md) |
| Configuração e execução | [.ia/operacao.md](.ia/operacao.md) |
| Testes e critérios de validação | [.ia/testes.md](.ia/testes.md) |
| Decisões, limitações e próximos passos | [.ia/decisoes-e-roadmap.md](.ia/decisoes-e-roadmap.md) |

O [README.md](README.md) é a entrada rápida para executar o projeto. A pasta
`.ia` descreve o contexto técnico e de negócio. Confira o código ao modificar
comportamento; se houver divergência, registre-a e atualize a documentação afetada.
Não trate propostas de evolução como funcionalidades implementadas.

## Mapa do código

- `services/vision/dock_vision/domain.py`: regras puras de zonas e consenso de placas.
- `services/vision/dock_vision/pipeline.py`: captura OpenCV, YOLO, ByteTrack e PaddleOCR.
- `services/vision/dock_vision/outbox.py`: persistência SQLite e envio HTTP em outro thread.
- `services/vision/dock_vision/simulation.py`: trajetórias e leituras sintéticas.
- `services/vision/dock_vision/__main__.py`: configuração, ciclo de vida e seleção do modo.
- `services/api/Program.cs`: Minimal API .NET 10, validação e projeção via Npgsql.
- `services/api/schema.sql`: criação inicial das tabelas e índices PostgreSQL.
- `config/zone.json`: polígono normalizado e parâmetros da doca.
- `compose.yaml`: containers `vision`, `api` e `postgres`.

## Regras para alterações

1. Preserve `domain.py` independente de câmera, modelos, HTTP e banco. A simulação
   e os testes de domínio devem continuar sem dependências de inferência.
2. Mantenha nomes de código e campos HTTP em inglês; escreva documentação em
   português, em UTF-8. O contrato HTTP usa `snake_case`.
3. Não transforme `tracking_lost` em `exited`, nem `observed_inside` em `entered`.
   Placa desconhecida deve continuar permitindo eventos e visitas.
4. Preserve a identidade por `event_id` e `visit_id`, a idempotência de reenvio e a
   transação que grava evento e atualiza permanência. Não correlacione visitas só
   pela placa ou pelo `track_id` numérico.
5. Use parâmetros nas consultas SQL. Mudanças no contrato exigem revisar produtor
   Python, consumidor .NET, projeção, testes de integração e documentação juntos.
6. Mudanças em tabelas existentes precisam de estratégia de migração: o
   `CREATE TABLE IF NOT EXISTS` atual não altera um banco já criado.
7. Mantenha as dependências pesadas no extra Python `vision` e no estágio Docker
   `inference`. Não acrescente broker, serviços ou abstrações sem necessidade do escopo.
8. Não inclua credenciais reais de RTSP, `.env`, vídeos, pesos ou bancos locais no
   versionamento. Use placeholders em exemplos e preserve dados existentes.
9. Evite editar artefatos gerados em `bin`, `obj`, `.cache` e `__pycache__`.
10. Atualize os documentos afetados na mesma mudança. Informe verificações
    executadas e limitações; não declare validação real com base na simulação.

## Verificação por tipo de mudança

Para Python, execute a partir de `services/vision`:

```powershell
uv run --no-project --python 3.11 python -m unittest discover -s tests -v
```

Para a API, execute a partir da raiz:

```powershell
dotnet build services/api/Dock.Api.csproj --configuration Release
```

Para contrato, persistência ou projeção, com API/PostgreSQL ativos, na raiz:

```powershell
uv run --no-project --python 3.11 python tests/api_smoke.py -v
```

Mudanças apenas em Markdown pedem revisão de conteúdo, comandos e links locais;
não exigem baixar modelos ou iniciar containers. Para código, acrescente testes
dos comportamentos relevantes e execute as verificações afetadas.

## Estado de validação conhecido

Na implementação inicial de 12/09/2026, passaram 18 testes Python e a compilação/
publicação local da API. A integração com PostgreSQL/Compose e a inferência real
não foram executadas naquele ambiente. Consulte [.ia/testes.md](.ia/testes.md)
e atualize esse registro quando novas evidências estiverem disponíveis.

