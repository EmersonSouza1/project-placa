# Regras de negócio

Fontes: [domínio Python](../services/vision/dock_vision/domain.py) e
[projeção da API](../services/api/Program.cs).

## Vocabulário e identidade

| Conceito | Significado |
|---|---|
| Doca | Área definida por um polígono na imagem |
| Track | Sequência de detecções associadas pelo tracker; não comprova identidade física |
| `stream_id` | UUID da execução do processador de zonas |
| `visit_id` | UUID de uma ocupação observada; reentrada gera outro UUID |
| `event_id` | UUID de um fato publicado; preservado em todas as tentativas de envio |
| Placa | Atributo opcional da observação, não chave de correlação da visita |

Cada visita mantém `camera_id`, `dock_id`, `stream_id` e `track_id` consistentes.
Não existe, nesta versão, uma restrição de somente uma visita aberta por doca.

## RN-01 — Confirmar a posição na zona

O ponto de referência é o centro inferior da caixa do veículo. O polígono usa
coordenadas de 0 a 1, possui pelo menos três pontos e área não nula; a borda conta
como dentro. A configuração deve conter um polígono simples: cruzamento de
arestas não é validado automaticamente.

Uma posição candidata deve persistir por `confirmation_seconds`, padrão de 1 s.
Oscilações reiniciam o tempo de confirmação. Uma observação ausente também
reinicia a candidatura, mas preserva o estado estável até expirar o track.
O horário do evento é o da confirmação, não o primeiro frame da candidatura.

## RN-02 — Gerar somente transições observadas

| Estado anterior | Observação confirmada | Resultado |
|---|---|---|
| Desconhecido | Fora | Arma o estado fora; nenhum evento |
| Desconhecido | Dentro | `observed_inside`, nova visita |
| Fora | Dentro | `entered`, nova visita |
| Dentro | Fora | `exited`, encerra a visita |
| Mesmo estado | Mesmo estado | Nenhum novo evento |

`observed_inside` indica início de observação, sem afirmar que a câmera viu a
entrada. `tracking_lost` nunca deve ser convertido automaticamente em saída.

## RN-03 — Tratar ausência e interrupção

O limite de ausência é `lost_after_seconds`, padrão de 5 s, maior que o tempo de
confirmação. Ao expirar, um track com visita ativa emite `tracking_lost`; um track
externo é apenas removido. Uma oclusão menor preserva a visita.

Desconexão de câmera, fim do arquivo ou encerramento que alcance a limpeza do
pipeline interrompem imediatamente visitas ativas. Queda abrupta pode deixar
permanências abertas, pois o estado dos tracks não é persistido.

## RN-04 — Derivar a permanência

| Dados recebidos | `status` | `duration_seconds` |
|---|---|---|
| Início, sem fim | `open` | `null` |
| Fim, sem início | `awaiting_start` | `null` |
| `entered` + `exited` | `completed` | Diferença em segundos entre fim e início |
| `observed_inside` + `exited` | `completed` | `null`: entrada real desconhecida |
| Qualquer início + `tracking_lost` | `interrupted` | `null` |

Fim recebido antes do início pode ser reconciliado posteriormente pelo mesmo
`visit_id`. Um fim com horário anterior ao início conhecido é conflitante e sua
transação é rejeitada. `ended_at` de uma interrupção não é horário de saída física.

## RN-05 — Reconhecer placa sem bloquear eventos

Eventos podem conter `plate=null` e `plate_confidence=null`. O Python transforma
texto em maiúsculas e remove espaços/hífens. São aceitos os formatos `ABC1234` e
`ABC1D23`; não há correção automática de ambiguidades como `O/0` e `I/1`.
Validar formato não comprova que uma placa existe em cadastro oficial.

Por track, cada candidato acumula soma de confiança e quantidade de observações.
Uma leitura precisa de confiança finita entre o mínimo configurado (0,7) e 1.
São necessárias pelo menos duas observações aceitas por candidato, por padrão.
Vence a maior soma; empates usam quantidade e depois ordem lexical do texto.
A confiança publicada é a média arredondada a quatro casas, não uma probabilidade
calibrada. O armazenamento admite até 64 candidatos distintos por track.

O adaptador fornece no máximo um voto por veículo por frame amostrado. O consenso
pode acumular enquanto o track está fora. Após uma saída, os votos são limpos.

## RN-06 — Enriquecer sem reescrever o histórico

A entrada leva o consenso disponível naquele momento. Leituras posteriores podem
aparecer na saída/interrupção, sem modificar o evento de entrada. A permanência
usa a placa não nula do evento mais recente por `occurred_at`; em empate, usa maior
confiança. Uma leitura nula posterior não apaga uma placa anterior.

Não existe evento específico para atualizar placa durante uma visita aberta.

## Diagnóstico com celular

O modo `ocr_test` procura texto com formato de placa na imagem inteira, sem
associação a veículo ou visita. Confirma duas leituras consecutivas com confiança
mínima de 0,7, até 15 segundos entre frames da mesma conexão. Seu resultado aparece
no `/health` como última detecção e horário UTC; não aplica regras de zona ou
permanência e não representa uma movimentação física. O consenso por track das
regras anteriores continua exclusivo do processamento normal de veículos.
