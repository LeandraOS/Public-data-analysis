# Case Técnico — Cientista de Dados · Transparência Brasil

Analisei 2.706 compras públicas de três medicamentos genéricos (AAS, Ácido
Fólico e Aciclovir), de dezembro de 2021 a julho de 2025. O trabalho tem
quatro partes: entender os problemas dos dados, tratá-los, responder três
perguntas sobre os preços pagos, e propor indicadores para acompanhar isso
de forma contínua.

**Para ver o trabalho completo:** abra
[`outputs/case_compras_medicamentos.html`](outputs/case_compras_medicamentos.html).
Ele tem o código, os gráficos e as explicações, e começa com um resumo em
linguagem simples antes de entrar em qualquer detalhe técnico.

**Se você tem só alguns minutos:** leia esse resumo no início do HTML, ou o
início do documento [`docs/00_respostas_case.md`](docs/00_respostas_case.md).

---

## Como rodar

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

pytest -q                    # roda os 37 testes, confirma que está tudo certo

jupyter nbconvert --to html --execute \
    notebooks/case_compras_medicamentos.ipynb \
    --output-dir outputs      # gera o relatório
```

## Onde está cada coisa

| Pergunta do case | Resposta |
|---|---|
| Como você coletaria esses dados de uma API? | `docs/01_arquitetura_coleta.md` |
| Os dados têm problemas? Quais? | seção 2 do notebook |
| Como você tratou esses problemas? | seção 3 do notebook, código em `src/preparacao.py` |
| O que os dados mostram? | seção 4 do notebook (três perguntas) |
| Que indicadores fariam sentido acompanhar? | seção 5 do notebook |
| Alguém consegue reproduzir isso? | este README + `tests/` |

O documento [`docs/00_respostas_case.md`](docs/00_respostas_case.md) tem a
versão só em texto de tudo isso, sem código, caso seja mais fácil de ler.

## O que encontrei

A base parece perfeita numa primeira olhada — nenhuma célula vazia, nenhuma
linha duplicada, todos os CNPJs válidos. O problema aparece quando você olha
com mais cuidado: existem três jeitos diferentes de marcar "sem informação"
no mesmo arquivo, um deles é literalmente um espaço em branco, invisível numa
tabela. Alguns preços estão claramente errados (uma compra registra R$
253.300 por um único comprimido — o valor do lote inteiro foi digitado no
campo de preço unitário). A mesma empresa aparece com nomes diferentes em
quase 50 casos. E encontrei três itens que mudaram de fornecedor depois de já
terem sido registrados, o que muda a forma de projetar qualquer coleta
automática dessa fonte.

Nada disso foi apagado. Cada problema virou uma marcação na base, e as
exclusões só acontecem no momento de calcular alguma coisa — sempre de forma
explícita, e sempre reversível.

Sobre os preços: o mesmo comprimido, do mesmo fabricante, custa até duas
vezes mais dependendo de quem compra — e a maior parte dessa diferença
acontece entre municípios do mesmo estado, não entre estados diferentes.
Comprar em grande quantidade ajuda, mas menos do que parece (dez vezes mais
volume baixa o preço uns 14%, não pela metade). Comprar por dispensa de
licitação, em vez de pregão, custa em média 18% mais caro no mesmo item. E
não há falta de concorrência entre fornecedores — o mercado é bem
distribuído. Juntando essas três coisas, a conclusão é que o problema está em
quem compra, não em quem vende, o que é uma notícia melhor do que parece:
significa que dá pra resolver com informação e organização, não só com
fiscalização.

## O que ficou de fora e por quê

O valor que apareceu na base é o valor homologado na licitação, não
necessariamente o que foi de fato pago depois — cruzar com o Portal da
Transparência resolveria isso. Também não corrigi os preços pela inflação,
porque não tinha uma base sólida pra escolher um índice específico para esses
três produtos; prefiro deixar isso declarado como limitação do que estimar
sem fundamento. E dois campos do dicionário de dados (`modalidade` e
`criterioJulgamento`) não vêm documentados nem em nenhum outro endpoint
público que encontrei — decodifiquei o significado deles por evidência
interna na própria base, mas isso é uma hipótese bem sustentada, não um fato
confirmado, e digo isso claramente em todo lugar onde ela é usada.

## Estrutura do repositório

```
├── data/                    dados originais e tratados
├── src/                     código: leitura → qualidade → tratamento → análise → indicadores → gráficos
├── notebooks/               o relatório completo, já executado
├── docs/                    a arquitetura de coleta, as decisões metodológicas, o dicionário de dados
├── tests/                   37 testes
└── outputs/                 o relatório em HTML, os gráficos, as tabelas
```

Cada etapa do código só depende da anterior — quem lê `analise.py` não
precisa entender como `qualidade.py` funciona por dentro, só o que ele
entrega.
