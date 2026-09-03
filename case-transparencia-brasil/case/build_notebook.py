"""Gera o notebook principal do case."""
import nbformat as nbf

nb = nbf.v4.new_notebook()
C = []
def md(t): C.append(nbf.v4.new_markdown_cell(t.strip()))
def code(t): C.append(nbf.v4.new_code_cell(t.strip()))

# ============================================================== CAPA
md(r"""
# Case Técnico — Cientista de Dados
## Compras públicas de medicamentos: qualidade, preços e indicadores

**Base:** `compras-gov.csv` — 2.706 itens de compra, classe CATMAT 6505 (Drogas e Medicamentos), dez/2021 a jul/2025.

---

### Como este documento está organizado

| Etapa | Onde está |
|---|---|
| **1 — Proposta de coleta** | `docs/01_arquitetura_coleta.md` (resumo na seção 1 abaixo) |
| **2 — Compreensão e qualidade** | seção 2 deste notebook |
| **3 — Preparação** | seção 3 |
| **4 — Análise** | seção 4 (três perguntas + análise temporal) |
| **5 — Indicadores** | seção 5 |
| **6 — Reprodutibilidade** | `README.md` + seção 6 |
| Decisões metodológicas | `docs/02_decisoes_metodologicas.md` |

O código de produção vive em `src/` e é **importado** aqui, não repetido:
`ingestao.py` (leitura) → `qualidade.py` (diagnóstico) → `preparacao.py`
(tratamento) → `analise.py` (análise) → `indicadores.py`. Essa separação é o
que atende ao requisito da Etapa 6 e o que permite testar cada camada
isoladamente.
""")

# ============================================================== SUMÁRIO EXECUTIVO
md(r"""
---
## Sumário executivo

**Qualidade dos dados.** A base é *estruturalmente* sólida e
*semanticamente* problemática. Não há uma única célula vazia, nenhuma linha
duplicada, nenhuma falha de conversão numérica e 100% dos CNPJs têm dígito
verificador válido. Mas:

- ausências existem, mas em **três formatos textuais diferentes** — `"NA"`,
  `" "` (um espaço, graficamente idêntico a vazio) e `"nan"` (um NaN de
  Python serializado como texto). Nenhum é reconhecido como nulo por padrão,
  o que faz a base parecer completa;
- **6,5% dos preços unitários são implausíveis**, e uma parte tem erro
  identificável: 15 registros lançaram o **valor total do lote** no campo de
  preço unitário (o extremo é R$ 253.300,00 por um comprimido de AAS);
- **48 CNPJs aparecem com mais de uma razão social**, o que inflaria a
  contagem de fornecedores e subestimaria a concentração de mercado;
- **11,6% do campo `marca` não contém marca** — contém texto de edital
  (`GENERICO`, `CONFORME TR`) e, em um caso, resíduo de HTML
  (`BRASTERAPICAjavascri`), indício de raspagem de tela na origem;
- `codigoMunicipio` chega como `4.108.403,00`, isto é, o código IBGE
  formatado como decimal — assinatura de passagem por planilha;
- três itens aparecem em **duas versões**, com fornecedor e quantidade
  diferentes: a fonte **retifica o passado**, o que determina toda a
  estratégia de coleta da Etapa 1.

**Três resultados analíticos.**

1. **Dispersão de preços.** Mesmo depois de restringir a produtos idênticos
   (mesmo CATMAT, mesma unidade de fornecimento) e remover implausíveis, o
   preço no percentil 90 é **1,8 a 2,3 vezes** o do percentil 10. Cerca de
   **90% dessa variação ocorre dentro da mesma UF**, não entre UFs: o
   problema é de informação e gestão local, não de custo regional.
2. **Economia de escala.** A elasticidade preço-quantidade é
   **−0,064** (IC 95%: −0,070 a −0,058; erros-padrão agrupados por unidade
   gestora), controlando item e ano. Multiplicar a quantidade por 10 reduz o
   preço unitário em ~**14%**. O sinal é estável nos três medicamentos e os
   consórcios intermunicipais pagam **~20% abaixo** da mediana do item-ano.
3. **Modalidade importa.** Compras por dispensa de licitação são
   **18% mais caras** que por pregão para o mesmo item, controlando ano,
   esfera, sistema de preços e quantidade (p < 0,001). No AAS, a diferença
   bruta de mediana chega a **+70%**.

**Quatro indicadores** são propostos na seção 5, todos robustos a outliers e
calculáveis trimestralmente: Índice de Preço Relativo (IPR), Índice de Preço
Ajustado por Escala (IPAE), Taxa de Contratação por Dispensa (TCD) e HHI de
Fornecimento.

**Limitação que atravessa tudo:** `quantidade × precoUnitario` é valor
**homologado**, não pago. Em registro de preços (88,7% da base), a ata
registra o preço e a quantidade máxima; o empenho pode ser parcial.
""")

# ============================================================== SETUP
md("---\n## 0. Ambiente e dependências")

code(r"""
import sys, platform, logging, warnings
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
import scipy
import statsmodels
from IPython.display import Image, display, Markdown

# O notebook é executado da raiz do repositório
if str(Path.cwd().name) == "notebooks":
    sys.path.insert(0, str(Path.cwd().parent))
    import os; os.chdir(Path.cwd().parent)

from src import ingestao, qualidade, preparacao, analise, indicadores, config

warnings.filterwarnings("ignore", category=FutureWarning)
logging.basicConfig(level=logging.WARNING)

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 60)
pd.set_option("display.float_format", lambda v: f"{v:,.4f}")

print(f"Python       {platform.python_version()}")
for m in (pd, np, scipy, statsmodels, matplotlib):
    print(f"{m.__name__:12s} {m.__version__}")
""")

# ============================================================== ETAPA 1
md(r"""
---
# Etapa 1 — Proposta de coleta de dados

A proposta completa está em **[`docs/01_arquitetura_coleta.md`](../docs/01_arquitetura_coleta.md)**,
com fluxograma, tabelas de decisão e política de erro por código HTTP. O
esqueleto comentado do coletor está em `src/coleta.py` (não executado).

### Resumo das decisões

**Três características da fonte determinam o desenho** — e as três foram
descobertas na análise da própria base, não assumidas:

1. **A fonte é mutável retroativamente.** 68% dos itens têm
   `dataHoraAtualizacaoItem` mais de um ano após `dataCompra`, e três
   registros aparecem em duas versões com fornecedor diferente.
   → O campo de controle da coleta tem de ser a data de **atualização**, não
   a data do fato; e o histórico precisa ser versionado (SCD tipo 2), para
   que retificações sejam auditáveis em vez de silenciosas.
2. **O dado passou por intermediários.** `codigoMunicipio` formatado como
   decimal, a string literal `'nan'` (um NaN de Python serializado) e resíduo
   de JavaScript em `marca` — três evidências convergentes.
   → Consumir a API diretamente e **preservar o payload bruto**.
3. **Coleta longa em API pública instável.**
   → Checkpoint por página, retry com backoff exponencial e *jitter*,
   circuit breaker, e rate limit no próprio cliente (não reagir ao 429).

**Arquitetura:** medalhão em três camadas.

- **Bronze** — JSON original comprimido, *append-only*, com versionamento de
  objeto e manifesto por execução (hash, parâmetros, contagens). Dado
  público que muda sem aviso só é auditável se alguém guardou a versão
  anterior.
- **Silver** — SCD tipo 2 por `idItemCompra`, carregado por **MERGE
  idempotente**. Reexecutar qualquer dia é seguro, o que torna o backfill
  trivial e permite sobreposição deliberada da janela de coleta.
- **Gold** — fato + dimensões + os indicadores da Etapa 5.

**Duas trilhas de coleta:** incremental diária (últimos 7 dias de
atualização, com folga sobre o watermark) e reconciliação mensal (24 meses),
que recupera retificações fora da janela.

**Schema drift:** contrato declarado em `config.SCHEMA_ESPERADO` e verificado
a cada carga. Campo novo é acolhido no bronze e alertado; campo removido
**falha** a promoção para silver; domínios (`modalidade`, etc.) são coletados
dos endpoints de referência e versionados como dimensão datada, nunca fixados
no código.

**Validação em três níveis:** completude da coleta (total lido = total
declarado pela API; nenhuma lacuna de página ou de mês), integridade
estrutural (unicidade de chaves, taxa de falha de parsing) e plausibilidade
(as 27 regras da seção 2). O que se monitora não é a taxa absoluta — 6,5% de
preços implausíveis é característica conhecida da fonte — mas a sua
**variação**.
""")

# ============================================================== ETAPA 2
md(r"""
---
# Etapa 2 — Compreensão e qualidade dos dados

## 2.1 Leitura e contrato de schema

A leitura preserva fidelidade ao original: **tudo como texto**, com
`keep_default_na=False`. As duas opções são deliberadas e explicadas no
código de `src/ingestao.py`. A mais importante: a fonte grava a **string
literal `"NA"`** como sentinela de ausência, e o comportamento padrão do
pandas a converteria em `NaN` antes de qualquer contagem — fazendo a base
parecer completa.
""")

code(r"""
df_bruto, meta = ingestao.ler_bruto()
print(f"Dimensões : {df_bruto.shape[0]:,} linhas x {df_bruto.shape[1]} colunas")
print(f"SHA-256   : {meta['sha256'][:32]}...")
print(f"Contrato  : {meta['schema']}")
""")

md(r"""
Contrato conforme: nenhuma coluna ausente, nenhuma inesperada, ordem
preservada. Numa coleta recorrente, este é o teste que transforma uma
mudança de estrutura da API em alerta, em vez de erro silencioso três
etapas adiante.

## 2.2 Granularidade

Primeira pergunta de qualquer base: **o que é uma linha?** Sem essa
declaração não existe agregação correta, porque não se sabe o que está sendo
contado.
""")

code(r"""
n = len(df_bruto)
print(f"Linhas                                    : {n:,}")
print(f"idItemCompra distintos                    : {df_bruto.idItemCompra.nunique():,}  -> chave primária válida")
print(f"idCompra distintos                        : {df_bruto.idCompra.nunique():,}")
print(f"Itens por compra (média / máx)            : {n/df_bruto.idCompra.nunique():.2f} / {df_bruto.idCompra.value_counts().max()}")
print(f"Pares (idCompra, numeroItemCompra) dup.   : {df_bruto.duplicated(['idCompra','numeroItemCompra']).sum()}  <-- investigar")
print(f"Linhas integralmente duplicadas           : {df_bruto.duplicated().sum()}")

print("\nCardinalidade das dimensões implícitas:")
for c, rotulo in [("codigoItemCatalogo","item de catálogo (CATMAT)"),
                  ("niFornecedor","fornecedor (CNPJ)"),
                  ("codigoUasg","unidade gestora (UASG)"),
                  ("codigoOrgao","órgão"),
                  ("codigoMunicipio","município"),
                  ("estado","UF"),
                  ("dataCompra","datas de compra distintas")]:
    print(f"  {rotulo:32s} {df_bruto[c].nunique():>6,}")
""")

md(r"""
**Grão declarado:** uma linha = **um item de uma compra pública**, na classe
CATMAT 6505, restrita a **três medicamentos**. A base é uma tabela-fato
desnormalizada — cada linha repete todos os atributos de todas as dimensões
(fornecedor, unidade gestora, município, item, tempo), todas em relação N:1
com o fato.

Dois pontos que mudam a leitura de tudo o que vem depois:

- **São só três moléculas**: Ácido Acetilsalicílico 100 mg, Ácido Fólico 5 mg
  e Aciclovir 200 mg. Todas genéricas, de baixo custo e alto volume. Nada
  aqui se generaliza para medicamentos de alto custo ou sob patente.
- **`codigoClasse` e `nomeClasse` são constantes** (6505 / DROGAS E
  MEDICAMENTOS): não são variáveis, são o *recorte da extração*. Viram
  metadado, não coluna.

Os 3 pares duplicados na chave de negócio são investigados na seção 3.3.
""")

code(r"""
# Os três itens da base
tab = (df_bruto.groupby(["codigoItemCatalogo","descricaoItem"])
       .agg(itens=("idItemCompra","size"),
            compradores=("codigoUasg","nunique"),
            fornecedores=("niFornecedor","nunique"))
       .reset_index())
display(tab)
""")

md("## 2.3 Perfilamento: completude, cardinalidade e tipos")

code(r"""
perfil = qualidade.perfilar_colunas(df_bruto)
display(perfil.style.format({"completude_%":"{:.1f}","cardinalidade_%":"{:.1f}","freq_modal_%":"{:.1f}"})
        .background_gradient(subset=["completude_%"], cmap="RdYlGn", vmin=0, vmax=100))
""")

md(r"""
### O que a tabela revela

**Nenhuma célula vazia, mas 5 colunas com ausência real.** Toda ausência
nesta base é a string `"NA"`:

| Coluna | `"NA"` | Leitura |
|---|---|---|
| `nomeUnidadeMedida` | 2.706 (100%) | coluna **nunca populada** — descartável |
| `siglaUnidadeMedida` | 2.689 (99,4%) | idem, praticamente vazia |
| `nomeUnidadeFornecimento` | 57 (2,1%) | **grave**: sem ela não se sabe a que o preço se refere |
| `esfera` | 57 (2,1%) | impede recorte por nível de governo |
| `municipio` | 9 (0,3%) | UF permanece utilizável |
| `codigoMunicipio` | 9 (`"nan"`) | mesmas linhas — ver a seguir |

**Colunas constantes** (`codigoClasse`, `nomeClasse`,
`capacidadeUnidadeFornecimento` em 99,4% igual a zero) não carregam
informação para nenhuma análise condicional — vão para a documentação, não
para a tabela.

**Baixa cardinalidade onde deveria ser alta:** `descricaoItem` tem 3 valores
distintos, confirmando o recorte estreito.

**Cardinalidade suspeita:** `niFornecedor` = 526 mas `nomeFornecedor` = 560.
Se o CNPJ identifica a empresa, não pode haver mais nomes que CNPJs. Isso é
investigado nas regras de consistência.
""")

md("## 2.4 Perfilamento numérico: robusto vs não robusto")

code(r"""
display(qualidade.perfilar_numericas(df_bruto).style.format(
    {c:"{:,.2f}" for c in ["min","p25","mediana","p75","p99","max","media",
                           "desvio_padrao","mad","assimetria","razao_max_mediana"]}))
""")

md(r"""
Esta tabela é, por si, um diagnóstico. Reportamos mediana e MAD **ao lado**
de média e desvio-padrão porque a divergência entre as duas famílias mede
contaminação por outliers:

- **`precoUnitario`**: mediana **R$ 0,06**, média **R$ 388** — a média é
  ~6.500× a mediana. Assimetria acima de 30. O máximo é **R$ 253.300,00**,
  4,2 milhões de vezes a mediana. Média e desvio-padrão têm ponto de ruptura
  0 (um único registro os desloca arbitrariamente); a mediana tem ponto de
  ruptura 50%. **Toda estatística de preço neste relatório é robusta.**
- **`quantidade`**: de 1 a 71 milhões de comprimidos. Faixa legítima — há
  desde um hospital militar comprando 40 unidades até um consórcio
  intermunicipal comprando para dezenas de municípios. Nenhuma quantidade
  foi excluída.
- **`percentualMaiorDesconto`**: 99,6% igual a zero. Os 11 valores não nulos
  são a chave para decodificar `criterioJulgamento` (seção 2.6).
- **0 falhas de parsing** em todas as colunas numéricas: o formato pt-BR é
  perfeitamente consistente.
""")

md(r"""
## 2.5 Avaliação sistemática: 27 regras em 6 dimensões

O diagnóstico é organizado nas dimensões clássicas de qualidade de dados
(Wang & Strong, 1996; Batini & Scannapieco, 2016; DAMA-DMBOK cap. 13):
**completude, unicidade, validade, consistência, acurácia e atualidade**.

Duas escolhas de projeto:

1. **Diagnóstico separado de tratamento.** Este passo apenas *mede e
   sinaliza*; nada é corrigido. Quem decide é a Etapa 3, e a decisão fica
   registrada na coluna `acao`. Isso evita o antipadrão de limpeza
   silenciosa, em que o número final não pode ser explicado.
2. **Regras declarativas.** Cada regra é uma função que devolve máscara
   booleana por linha (espírito de Great Expectations / testes dbt). Isso
   dá contagem agregada *e* marcação por linha para auditoria — e as mesmas
   regras servem como suíte de monitoramento na coleta recorrente (Etapa 1).
""")

code(r"""
relatorio, marcacoes = qualidade.avaliar(df_bruto)
cores = {"bloqueante":"background-color:#ffcdd2","alta":"background-color:#ffe0b2",
         "media":"background-color:#fff9c4","informativa":"background-color:#e8f5e9"}
display(relatorio.style
        .apply(lambda r: [cores.get(r.severidade,"")]*len(r), axis=1)
        .format({"taxa_%":"{:.2f}"}))
""")

code(r"""
display(qualidade.indice_qualidade(relatorio))
print("\nRegras violadas por severidade:")
print(relatorio.query("violacoes > 0").severidade.value_counts().to_string())
""")

md(r"""
### Interpretação dos achados

**Nenhuma regra bloqueante violada.** Não há linha duplicada, `idItemCompra`
é chave primária válida, todo preço e toda quantidade são positivos e
conversíveis, e **todos os 526 CNPJs passam na validação de dígito
verificador** (módulo 11). Isso importa além da estética: CNPJ válido é
pré-requisito para integrar a base com cadastros externos (Receita Federal,
CEIS/CNEP) — ver `docs/02_decisoes_metodologicas.md`, §11.

**Os seis problemas que afetam a análise, em ordem de severidade:**

| # | Achado | Escala | Consequência |
|---|---|---|---|
| 1 | Preços implausíveis (`ACUR-01`, `ACUR-02`) | 178 registros (6,6%) | inviabiliza média; exige estatística robusta |
| 2 | CNPJ com múltiplas razões sociais (`CONS-01`) | 424 registros / 48 CNPJs | inflaria contagem de fornecedores, subestimaria concentração |
| 3 | `marca` sem marca (`VALD-06`) | 314 registros (11,6%) | inviabiliza análise por laboratório |
| 4 | Unidade de fornecimento ausente ou divergente (`COMP-01`, `CONS-08`) | 84 registros | preço não comparável |
| 5 | Espaço de padding em campo de texto (`VALD-07`) | 102 células | cria categoria fantasma invisível a olho nu |
| 6 | Duplicidade na chave de negócio (`UNIC-02`) | 3 pares | inflaria valor e contagem |

**Dois achados de consistência que são *boas* notícias**, e que só aparecem
porque foram testados: `codigoUasg → nomeUasg` é dependência funcional
perfeita, e `codigoMunicipio → estado` é 100% consistente com o prefixo IBGE
de UF (`CONS-03`, 0 violações em 2.697 códigos válidos). As dimensões
território e unidade gestora são confiáveis.

**Dois achados que são informação, não erro:** `CONS-04` e `CONS-05`, tratados
a seguir.

**`ATUAL-01` — 68% dos itens atualizados mais de um ano após a compra.** Não
é erro: é a característica mais importante da fonte para o desenho da Etapa 1.
A fonte **retifica o passado**.
""")

md(r"""
### Os três formatos de ausência — e por que um deles quase passou

A base não tem uma única célula vazia. Tem **três sentinelas textuais
distintas**, e as duas últimas foram descobertas por um teste automatizado
falhar, não por inspeção visual:
""")

code(r"""
print("1. 'NA' — sentinela declarada pela fonte:")
for c in ["nomeUnidadeMedida","siglaUnidadeMedida","nomeUnidadeFornecimento","esfera","municipio"]:
    n = df_bruto[c].str.strip().eq("NA").sum()
    print(f"   {c:26s} {n:>5,}")

print("\n2. ' ' — célula com apenas um espaço (graficamente idêntica a vazio):")
pad = qualidade.padding_em_branco(df_bruto)
for c in ["criterioJulgamento","marca"]:
    sc = df_bruto[c].astype("string")
    n = (sc != sc.str.strip()).sum()
    if n: print(f"   {c:26s} {n:>5,}")
print(f"   valores distintos em criterioJulgamento: {[repr(x) for x in df_bruto.criterioJulgamento.unique()]}")

print("\n3. 'nan' — a string literal, um NaN de Python serializado como texto:")
alvo = df_bruto.codigoMunicipio.astype('string').str.strip().eq('nan')
print(f"   codigoMunicipio            {alvo.sum():>5,}")
display(df_bruto.loc[alvo, ["municipio","estado","codigoMunicipio","nomeUasg"]].head(4))
""")

md(r"""
**Por que isso importa mais do que parece.**

O caso 2 é o mais traiçoeiro: `criterioJulgamento` guarda `' '`, não `''`.
Espaço e vazio são **graficamente idênticos** — em qualquer tabela, gráfico ou
inspeção visual, os dois aparecem como nada. Mas para o computador são
valores distintos: `== ""`, `isin([""])`, um `GROUP BY` ou um `JOIN` tratam
`' '` como uma **categoria fantasma**.

Foi assim que este problema apareceu aqui: a regra `CONS-04` acusava 74
violações que o cruzamento de frequências da seção 2.6 não mostrava. A
divergência era exatamente o espaço. O achado virou a regra `VALD-07` e um
teste de regressão em `tests/test_pipeline.py` — e é o argumento mais
concreto a favor de manter uma suíte de testes sobre dados, e não apenas
olhar tabelas.

O caso 3 é o mais informativo sobre a **procedência** do arquivo. A string
`'nan'` não é um valor que uma API REST produza: é o que sai quando um
`float('nan')` de Python é convertido em texto. Somado a `codigoMunicipio`
formatado como decimal (`4.108.403,00`) e ao `BRASTERAPICAjavascri` em
`marca`, forma um conjunto de evidências convergentes: **o arquivo passou por
pelo menos um script e/ou planilha entre a API e a entrega.** É precisamente
o que a arquitetura da Etapa 1 elimina, ao consumir a API diretamente e
preservar o payload bruto.

**Decisão:** os três formatos são normalizados na tipagem
(`config.SENTINELAS_NULAS`), com `strip` aplicado antes de qualquer
comparação. Depois disso, `CONS-04` e `CONS-05` passam a 0 violações — o que
confirma as dependências funcionais usadas na próxima seção.
""")

md(r"""
## 2.6 Decodificando campos que o dicionário não documenta

O dicionário fornecido marca `criterioJulgamento` como "NA" e não descreve os
códigos de `modalidade`. Em vez de descartar os campos, é possível inferir a
semântica por **evidência interna** — e reportar como hipótese, não como fato.
""")

code(r"""
print("Evidência 1 — dependência funcional modalidade -> criterioJulgamento:")
crit = df_bruto.criterioJulgamento.str.strip().replace("", "(vazio)")
ct = pd.crosstab(df_bruto.modalidade, crit)
display(ct)

print("Evidência 2 — criterioJulgamento == 'D' <-> percentualMaiorDesconto > 0:")
desconto = qualidade.para_numero_br(df_bruto.percentualMaiorDesconto) > 0
display(pd.crosstab(crit, desconto,
                    rownames=["criterioJulgamento"], colnames=["desconto > 0"]))
""")

md(r"""
### A inferência

Duas dependências **perfeitas**, sem uma única exceção em 2.706 linhas:

1. `modalidade = 5` → critério é sempre `V` ou `D`; `modalidade = 6` → critério
   é sempre vazio ou `1`. Ou seja: a modalidade 5 **tem** critério de
   julgamento; a 6 **não tem**.
2. `criterioJulgamento = 'D'` ⟺ `percentualMaiorDesconto > 0`, coerente nas
   duas direções (10/10). Nenhum desconto sem o critério `D`, nenhum `D` sem
   desconto.

**Leitura:** `D` = *maior desconto*, `V` = *menor preço/valor*. Um
procedimento que tem critério de julgamento é competitivo; um que não tem,
não é. Somando a distribuição (96,6% na modalidade 5, esperado para
medicamentos sob a Lei 14.133/2021) e o achado da Etapa 4 — a modalidade 6 é
**18% mais cara** controlando item, ano, esfera e quantidade, exatamente o
que a teoria prevê para contratação sem competição — a leitura mais provável
é:

> **modalidade 5 = Pregão · modalidade 6 = Dispensa de licitação**

**Status: hipótese**, sustentada por três evidências independentes e
convergentes, não fato confirmado. Registrada como hipótese em
`config.DOM_MODALIDADE`, sinalizada em toda a apresentação e listada como
limitação do indicador IND-03. Antes de publicação, deve ser confirmada
contra a tabela de domínio da API — que, na arquitetura da Etapa 1, é
coletada e versionada justamente para evitar esse tipo de inferência.
""")

md(r"""
## 2.7 Valores extremos: três problemas diferentes, não um

O extremo do `precoUnitario` — R$ 253.300,00 por um comprimido de AAS —
poderia ser descartado como "outlier". Investigar em vez de descartar revela
que há **três fenômenos distintos**, que exigem tratamentos distintos.
""")

code(r"""
p = qualidade.para_numero_br(df_bruto.precoUnitario)
q = qualidade.para_numero_br(df_bruto.quantidade)

print("Achado 1 — quantidade = 1 concentra os preços absurdos")
print(pd.DataFrame({
    "n": [(q==1).sum(), (q>1).sum()],
    "preço mediano": [p[q==1].median(), p[q>1].median()],
    "preço máximo": [p[q==1].max(), p[q>1].max()],
}, index=["quantidade = 1", "quantidade > 1"]).to_string())

print("\nOs 6 maiores preços da base:")
display(df_bruto.assign(preco=p, qtd=q).nlargest(6,"preco")[
    ["descricaoItem","preco","qtd","nomeUnidadeFornecimento","nomeUasg","estado"]])
""")

md(r"""
**Achado 1 — o valor do lote foi lançado no campo de preço unitário.**
Os 15 registros com `quantidade = 1` têm preço mediano de **R$ 2.673,77**,
contra R$ 0,06 nos demais. "Comprou 1 comprimido de AAS por R$ 253.300" não
é um preço: é o valor total do lote no campo errado.

O ponto metodológico importa mais que o achado: **nenhum dos dois sinais
isolados é conclusivo.** Comprar 1 unidade é legítimo (hospitais militares o
fazem); preço alto pode ser item caro. É a **conjunção** — quantidade 1 *e*
preço >100× a mediana do mesmo CATMAT — que identifica o erro. Regra
`ACUR-02`.
""")

code(r"""
print("Achado 2 — o preço só é comparável dentro da mesma unidade de fornecimento")
display(df_bruto.assign(preco=p).groupby("nomeUnidadeFornecimento")["preco"]
        .agg(n="size", mediana="median", minimo="min", maximo="max")
        .sort_values("n", ascending=False))
""")

md(r"""
**Achado 2 — comparar R$ 2,40 (bisnaga) com R$ 0,06 (comprimido) é comparar
embalagens, não preços.** E há um agravante: a descrição CATMAT dos três itens
especifica dosagem **oral** ("ACICLOVIR, DOSAGEM: 200 MG"), o que é
**incompatível** com bisnaga (pomada) e frasco-ampola (injetável). Ou o item
foi classificado no CATMAT errado, ou a unidade foi preenchida errada.
Nos dois casos, o registro não é comparável — regra `CONS-08`.
""")

code(r"""
print("Achado 3 — no critério 'maior desconto', precoUnitario mede outra coisa")
display(df_bruto.loc[df_bruto.criterioJulgamento=="D",
        ["descricaoItem","precoUnitario","percentualMaiorDesconto","quantidade","nomeUasg"]])
""")

md(r"""
**Achado 3 — semântica divergente.** Preço de R$ 1,15 com 82,61% de desconto;
R$ 0,19 com 84%. Os dois campos são inconsistentes entre si, o que sugere que
nesse critério `precoUnitario` seja o preço **de referência do edital**, não
o homologado. Esses 10 registros são excluídos das estatísticas de preço não
por serem implausíveis, mas por **medirem coisa diferente** — confundir preço
de referência com preço pago enviesaria o resultado para cima.

### Método de detecção: escore-z modificado sobre log(preço), por item

Para o que resta — preços implausíveis sem assinatura clara — usamos o escore
de **Iglewicz & Hoaglin (1993)**: `0,6745·(x − mediana)/MAD`, com limiar 3,5.
Três escolhas, cada uma necessária:

- **Escore modificado, não z-score clássico.** O z-score usa média e
  desvio-padrão, ambos com ponto de ruptura 0. O registro de R$ 253.300 infla
  o desvio-padrão o suficiente para *ele próprio* deixar de parecer extremo —
  o fenômeno de **masking**. Mediana e MAD têm ponto de ruptura 50%.
- **Em log.** A distribuição é assimétrica à direita e o processo gerador é
  multiplicativo. Em nível, um limiar simétrico rejeitaria preços altos
  legítimos e não detectaria preços baixos suspeitos.
- **Estratificado por CATMAT.** O Aciclovir custa ~4× o AAS. Um limiar global
  classificaria *todo* o Aciclovir como outlier: mediria heterogeneidade
  entre produtos, não anomalia dentro de um produto.
""")

# ============================================================== ETAPA 3
md(r"""
---
# Etapa 3 — Preparação dos dados

**Princípio: nada é apagado.** Registros problemáticos recebem colunas de
marcação (`flag_*`) e uma classificação de escopo. As exclusões acontecem no
ponto de uso, por filtro explícito. Assim qualquer número é reconciliável
com as 2.706 linhas originais, e qualquer decisão é revertida mudando um
parâmetro em `src/config.py`.

O pipeline (`src/preparacao.py`) encadeia seis passos, cada um uma decisão
metodológica única e reversível, com log de linhagem.
""")

code(r"""
df, metap = preparacao.preparar(df_bruto)
display(metap["linhagem"])
""")

md(r"""
## 3.1 Tipagem

- **Numéricas pt-BR** → float. Ordem obrigatória: remover milhar (`.`), depois
  trocar decimal (`,` → `.`). O inverso corromperia o valor. **0 falhas.**
- **Datas** → UTC (a fonte grava offset `Z`). Manter tudo em UTC evita
  comparar instantes com fusos distintos; conversão para hora local só na
  apresentação.
- **Identificadores** → permanecem texto. São rótulos, não grandezas: média
  de CNPJ não significa nada, e a conversão numérica destruiria zeros à
  esquerda.
- **`codigoMunicipio`** → reconstituído. Chega como `"4.108.403,00"`: o
  código IBGE de 7 dígitos formatado como *decimal*. Isso não é formato de
  API — é assinatura de passagem por planilha entre a fonte e o arquivo.
  Recuperamos a parte inteira e validamos comprimento e prefixo de UF.
""")

code(r"""
print("Colunas descartadas (sem informação):")
display(metap["colunas_descartadas"])
""")

md(r"""
## 3.2 Colunas descartadas

`nomeUnidadeMedida` é 100% ausente. `codigoClasse` e `nomeClasse` são
constantes — não são variáveis, são o **recorte da extração**, e viram
metadado. Uma coluna constante não carrega informação para nenhuma análise
condicional.

## 3.3 Duplicidade: versões, não cópias

Os 3 pares que violam `(idCompra, numeroItemCompra)`:
""")

code(r"""
display(metap["versoes_antigas"][["idCompra","idItemCompra","numeroItemCompra",
        "quantidade","precoUnitario","nomeFornecedor","dataHoraAtualizacaoItem"]])

chave = ["idCompra","numeroItemCompra"]
ambas = df_bruto[df_bruto.duplicated(chave, keep=False)].sort_values(chave)
display(ambas[["idCompra","idItemCompra","numeroItemCompra","quantidade",
               "precoUnitario","nomeFornecedor","dataHoraAtualizacaoItem"]])
""")

md(r"""
Mesma compra, mesmo número de item, `idItemCompra` diferentes — e
**fornecedor diferente**, com quantidade 10× diferente num dos casos
(107.280 → 1.072.800). Não são cópias: são duas **versões** do mesmo registro
no tempo. O registro foi retificado na origem e a extração preservou ambas.

**Decisão:** manter a versão mais recente por `dataHoraAtualizacaoItem`
(SCD tipo 1, Kimball). Contar as duas inflaria valor e contagem de itens. As
três versões antigas ficam disponíveis em `metap['versoes_antigas']`, não
apagadas.

**Consequência para a Etapa 1:** este é o achado que determina a estratégia
de coleta. A fonte é mutável retroativamente ⇒ o coletor precisa usar
`dataHoraAtualizacaoItem` como campo de controle e versionar o histórico
(SCD tipo 2), para que retificações sejam auditáveis.

## 3.4 Identidade do fornecedor: CNPJ, não nome
""")

code(r"""
print(f"CNPJs distintos          : {df.niFornecedor.nunique()}")
print(f"Razões sociais distintas : {df.nomeFornecedor.nunique()}   <-- mais nomes que CNPJs")
print(f"Raízes de CNPJ (grupos)  : {df.raizCnpj.nunique()}")
print(f"CNPJs com >1 razão social: {(df.groupby('niFornecedor').nomeFornecedor.nunique()>1).sum()}")

g = df.groupby("niFornecedor").nomeFornecedor.unique()
print("\nExemplos:")
for ni in df.niFornecedor[df.niFornecedor.isin(
        (h:=df.groupby('niFornecedor').nomeFornecedor.nunique())[h>1].index)].unique()[:5]:
    print(f"  {ni} -> {list(g[ni])}")
""")

md(r"""
**Três causas distintas**, todas visíveis nos exemplos:

1. **Mudança de tipo societário** — a Lei 14.195/2021 extinguiu a EIRELI e
   converteu automaticamente milhares de empresas em LTDA. Daí
   `ASLI COMERCIAL EIRELI` / `ASLI COMERCIAL LTDA`.
2. **Alteração de razão social** — `CIMED INDUSTRIA DE MEDICAMENTOS LTDA` →
   `CIMED INDUSTRIA S.A.`
3. **Truncamento do campo** no registro mais antigo — `DENTAL ALENCAR
   IMPORTACAO E EXPORTACAO COMERCIO E REPRE` (corta em 54 caracteres).

**Decisão:** a identidade é o CNPJ. Nome canônico = grafia do registro mais
recente — regra determinística e reproduzível, preferível a "a mais
frequente" (empata em vários casos) ou "a mais longa" (arbitrária).

**Decisão complementar:** 526 CNPJs = 511 raízes, ou seja 15 pares
matriz/filial. Análises de **concentração** usam a raiz (o grupo econômico é
o agente relevante); análises de **contratação** usam o CNPJ completo (o
estabelecimento é quem contrata).

**O que NÃO foi feito:** deduplicação difusa por nome. Com CNPJ disponível e
validado, casamento probabilístico só adicionaria falsos positivos —
"CIRURGICA SANTA CRUZ" e "CIRURGICA SANTA CRUZ COM. DE PRODUTOS
HOSPITALARES" podem ser a mesma empresa ou duas, e o CNPJ resolve sem
inferência.

## 3.5 O campo `marca`: normalizado, mas não usado
""")

code(r"""
print(f"Valores distintos, cru        : {df.marca.nunique()}")
print(f"Valores distintos, normalizado: {df.marcaNormalizada.nunique()}")
print(f"Registros sem marca real      : {(~df.marcaInformativa).sum()} ({100*(~df.marcaInformativa).mean():.1f}%)")
print("\nValores mais frequentes classificados como NÃO informativos:")
print(df.loc[~df.marcaInformativa,"marca"].value_counts().head(12).to_string())
print("\nResíduo de extração:")
print(df.loc[df.marca.str.contains("javascri", case=False, na=False),"marca"].unique())
""")

md(r"""
A normalização canônica (maiúsculas → sem diacríticos → sem pontuação →
espaços colapsados) reduz 501 valores a 380. Mas o problema real não é
ortográfico: **11,6% dos registros não contêm marca alguma.** O campo mistura
três coisas:

1. marca comercial de fato — `HIPOLABOR`, `NATULAB`, `PRATI DONADUZZI`;
2. texto de edital — `GENERICO` (127 registros somando variantes),
   `COMPRIMIDO` (105), `CONFORME TR`, `SIMILAR`, `A DEFINIR`;
3. **ruído de extração** — `BRASTERAPICAjavascri`, resíduo de HTML/JavaScript.

O item 3 é o mais relevante para a Etapa 1: é evidência de **raspagem de
tela** em algum ponto da cadeia, e reforça a decisão de consumir a API
diretamente e preservar o payload bruto.

**Decisão:** `marca` **não é dimensão analítica**. Qualquer análise "por
laboratório" criaria uma categoria fantasma `GENÉRICO` com 127 registros
competindo com laboratórios reais.

## 3.6 Escopo de análise de preços

A decisão mais consequente da preparação. `escopo_preco` responde a uma única
pergunta: *este registro pode entrar numa estatística de preço unitário?*
""")

code(r"""
esc = metap["distribuicao_escopo"]
display(pd.DataFrame({"registros": esc, "%": (100*esc/len(df)).round(1)}))

dfp = preparacao.base_precos(df)
print(f"\nBase completa (todas as análises não monetárias): {len(df):,} registros")
print(f"Escopo comparável (estatísticas de preço)       : {len(dfp):,} registros ({100*len(dfp)/len(df):.1f}%)")
""")

md(r"""
| Escopo | n | Por que fora |
|---|---|---|
| `comparavel` | 2.455 | — |
| `preco_implausivel` | 160 | \|escore-z modificado\| > 3,5 e/ou assinatura de valor de lote |
| `unidade_divergente` | 84 | unidade não comparável a comprimido/cápsula, ou ausente |
| `criterio_desconto` | 4 | `precoUnitario` mede o preço de referência, não o pago |

Registros fora do escopo de preço **continuam na base** e são usados em todas
as análises que não dependem de preço: contagem de itens, cobertura
territorial, concentração de fornecedores, taxa de dispensa.

## 3.7 Variáveis derivadas
""")

code(r"""
novas = ["valorTotalItem","logPrecoUnitario","logQuantidade","anoCompra","trimestreCompra",
         "raizCnpj","cnpjValido","fornecedorCanonico","marcaInformativa","ehConsorcio",
         "itensNaCompra","diasAteAtualizacao","modalidadeDesc","esferaDesc","escopo_preco"]
display(df[novas].head(4).T)
print(f"\nValor total registrado na base: R$ {df.valorTotalItem.sum():,.2f}")
print(f"Período coberto: {df.dataCompra.min():%d/%m/%Y} a {df.dataCompra.max():%d/%m/%Y}")
""")

md(r"""
**Advertência sobre `valorTotalItem = quantidade × precoUnitario`:** é uma
**reconstrução**, não campo da fonte. É o valor *homologado* do item, que
**não equivale a valor pago**. Em compras via SISRP (registro de preços —
88,7% da base), a ata registra o preço e a quantidade *máxima*; o empenho
posterior pode ser parcial ou nulo. Toda leitura financeira aqui é de valor
**contratado/registrado**, e é assim que os resultados são reportados.
""")

# ============================================================== ETAPA 4
md(r"""
---
# Etapa 4 — Análise dos dados

Três perguntas, cada uma com relevância, método, resultado, interpretação e
limitações. Todas usam o escopo comparável para preços e a base completa para
o resto.
""")

md(r"""
## Pergunta 1 — Quanto varia o preço do mesmo medicamento entre compradores?

### Relevância
Medicamentos com o mesmo código CATMAT, mesma dosagem e mesma unidade de
fornecimento são **bens homogêneos**. Num mercado competitivo com informação
disponível, o preço deveria convergir. Dispersão persistente em compras
públicas de bens homogêneos é o objeto central da literatura de
**desperdício passivo** (Bandiera, Prat & Valletti, 2009): sobrepreço que
decorre de gestão e informação deficientes, não necessariamente de corrupção.
É também a base da pesquisa de preços obrigatória (Lei 14.133/2021, art. 23):
se o gestor conhecesse a distribuição nacional, não compraria no percentil 90.

### Método
Estatísticas robustas por item — mediana, MAD normalizado (MADN, comparável a
um desvio-padrão), razão interdecil **P90/P10** e coeficiente de dispersão
robusto. Preferimos o interdecil ao coeficiente de variação porque este
último é definido a partir de média e desvio-padrão, ambos não robustos.
Adicionalmente, decompomos a variância de log(preço) em componente
**entre-UF** e **intra-UF**, para localizar onde a dispersão mora.
""")

code(r"""
r1 = analise.p1_dispersao_precos(dfp)
display(r1["tabela"].style.format({
    "preco_min":"R$ {:.3f}","P10":"R$ {:.3f}","mediana":"R$ {:.3f}",
    "P90":"R$ {:.3f}","preco_max":"R$ {:.3f}","MADN":"{:.4f}",
    "disp_robusta_%":"{:.1f}%","razao_P90_P10":"{:.2f}x","razao_max_min":"{:.2f}x"}).hide(axis="index"))
""")

code(r"""
display(Image(str(r1["figuras"][0])))
""")

code(r"""
print("Decomposição da variância de log(preço):")
display(r1["decomposicao"].style.format({"var_entre_UF_%":"{:.1f}%","var_intra_UF_%":"{:.1f}%"}).hide(axis="index"))
display(Image(str(r1["figuras"][1])))
""")

md(r"""
### Resultados

| Medicamento | n | P10 | mediana | P90 | P90/P10 | máx/mín |
|---|---|---|---|---|---|---|
| Ácido Fólico 5 mg | 799 | R$ 0,03 | R$ 0,04 | R$ 0,06 | **2,00×** | 6,0× |
| AAS 100 mg | 829 | R$ 0,03 | R$ 0,05 | R$ 0,07 | **2,33×** | 7,5× |
| Aciclovir 200 mg | 827 | R$ 0,16 | R$ 0,20 | R$ 0,29 | **1,81×** | 5,1× |

E a decomposição de variância mostra que **~90% da dispersão ocorre dentro da
mesma UF**, não entre UFs.

### Interpretação

**Isto é depois da limpeza.** Os R$ 253.300 já foram removidos; os 160
registros implausíveis, também. O que sobra é dispersão entre compras
tecnicamente comparáveis do mesmo produto — e ela é de **2× entre o decil
mais barato e o mais caro**, com amplitude total de 5 a 7,5 vezes.

Dois pontos importam:

1. **A dispersão é local, não regional.** Se ~90% da variação está *dentro*
   da UF, a explicação não é custo logístico ou diferença de mercado
   regional: é heterogeneidade de capacidade de compra entre entes vizinhos.
   Municípios do mesmo estado, comprando o mesmo comprimido, pagam preços
   que diferem por um fator de 2. Isso é exatamente o que a literatura
   chama de desperdício passivo — e é **acionável**: o remédio é informação
   e agregação, não fiscalização.
2. **A magnitude absoluta parece pequena e não é.** A diferença entre
   R$ 0,03 e R$ 0,07 por comprimido é irrelevante para um consumidor e
   material para o Estado: aplicada ao volume da base (o AAS soma dezenas de
   milhões de comprimidos por ano), cada centavo é da ordem de centenas de
   milhares de reais.

O gráfico por UF é deliberadamente apresentado como **índice relativo à
mediana nacional de cada item**, não como preço absoluto: sem essa
normalização, uma UF que compra mais Aciclovir (item ~4× mais caro) apareceria
como "caríssima" por composição de cesta, não por preço.

### Limitações
- **O benchmark é endógeno.** A mediana é da própria base. Se o mercado
  inteiro pagar acima do razoável, a análise não detecta. Corrigir exige
  benchmark exógeno — o preço máximo regulado da CMED/ANVISA
  (`docs/02_decisoes_metodologicas.md`, §11).
- **Preços nominais.** Sem deflator, parte da dispersão entre 2021 e 2025 é
  inflação. Mitigado nas análises seguintes por efeito fixo de ano.
- **Não controla quantidade.** Compras pequenas são legitimamente mais caras
  — exatamente o que a Pergunta 2 mede e o indicador IND-02 corrige.
- **Não controla atributos não observados**: prazo de entrega, exigências de
  embalagem, custo logístico para municípios remotos.
""")

md(r"""
## Pergunta 2 — Existe economia de escala? De que tamanho?

### Relevância
É a hipótese que sustenta a política de **centralização de compras** e os
**consórcios intermunicipais de saúde**. Se a elasticidade for próxima de
zero, fragmentar a compra entre 5.570 municípios é barato. Se for negativa e
relevante, a pulverização tem custo fiscal mensurável, e a agregação passa a
ser recomendação com base empírica — não intuição administrativa.

### Método
Regressão log-log:

$$\log(\text{preço}_i) = \alpha + \beta \log(\text{quantidade}_i) + \gamma_{\text{item}} + \delta_{\text{ano}} + \varepsilon_i$$

- $\beta$ é a **elasticidade preço-quantidade**: variação percentual do preço
  para 1% de variação na quantidade. A forma log-log é a especificação
  canônica para elasticidade e estabiliza a assimetria das duas variáveis.
- **Efeitos fixos de item CATMAT** absorvem o nível de preço de cada
  medicamento. Sem eles, $\beta$ capturaria apenas o fato de o AAS ser barato
  *e* comprado em grande volume — viés de variável omitida clássico.
- **Efeitos fixos de ano** absorvem inflação e choques de mercado.
- **Erros-padrão agrupados por UASG**: itens da mesma compra e do mesmo
  comprador não são observações independentes. Ignorar isso subestimaria os
  erros-padrão (Moulton, 1990; Cameron & Miller, 2015).

Complementarmente, uma visão **não paramétrica** (quintis de quantidade
dentro de cada item) e a correlação de Spearman — que não impõe forma
funcional alguma.
""")

code(r"""
r2 = analise.p2_economia_escala(dfp)
e = r2["efeitos"]
print(f"Elasticidade preço-quantidade (β) : {e['elasticidade']:+.4f}")
print(f"IC 95% (cluster por UASG)         : [{e['ic95_inf']:+.4f}, {e['ic95_sup']:+.4f}]")
print(f"p-valor                           : {e['p_valor']:.2e}")
print(f"R² / n                            : {e['r2']:.3f} / {e['n']:,}")
print()
print(f"Efeito de DOBRAR a quantidade     : {e['efeito_dobrar_qtd_%']:+.1f}% no preço unitário")
print(f"Efeito de MULTIPLICAR POR 10      : {e['efeito_10x_qtd_%']:+.1f}% no preço unitário")
""")

code(r"""
print("Estabilidade do resultado — elasticidade estimada separadamente por medicamento:")
display(r2["por_item"].style.format({
    "elasticidade":"{:+.4f}","ic95_inf":"{:+.4f}","ic95_sup":"{:+.4f}",
    "spearman":"{:+.3f}","p_spearman":"{:.1e}"}).hide(axis="index"))
display(Image(str(r2["figuras"][0])))
""")

code(r"""
print("Visão não paramétrica — preço mediano por quintil de quantidade (dentro de cada item):")
display(r2["quintis"].style.format("R$ {:.4f}"))
print("\nQuantidade mediana de cada quintil:")
display(r2["quintis_qtd"].to_frame("quantidade mediana").style.format("{:,.0f}"))
display(Image(str(r2["figuras"][1])))
""")

code(r"""
print("Consórcios intermunicipais de saúde — agregação institucionalizada:")
display(r2["consorcios"].rename(index={False:"demais entes", True:"consórcios"})
        .style.format({"razao_mediana":"{:.2f}","qtd_mediana":"{:,.0f}"}))
""")

md(r"""
### Resultados

**β = −0,064** (IC 95%: −0,070 a −0,058; p < 10⁻⁹⁰; n = 2.455). Traduzindo:

- dobrar a quantidade → preço unitário **−4,3%**;
- multiplicar a quantidade por 10 → preço unitário **−13,7%**.

O resultado é **estável**: estimado separadamente, β fica entre −0,056 e
−0,070 nos três medicamentos, com intervalos de confiança que se sobrepõem.
Spearman entre −0,42 e −0,57 confirma o sinal **sem impor forma funcional**.
A visão por quintis é monotônica em todos os três: o quintil de maior volume
paga consistentemente menos que o de menor.

**Consórcios intermunicipais** compram uma quantidade mediana de ~488 mil
unidades e pagam **razão 0,80** — 20% abaixo da mediana do item-ano.

### Interpretação

Há gradiente de escala claro, robusto e consistente. Mas a magnitude precisa
ser lida com cuidado, nos dois sentidos:

**É menor do que a intuição sugere.** Uma elasticidade de −0,064 significa
que ganhos de escala são **reais mas modestos**: agregar dez municípios não
corta o preço pela metade, corta ~14%. Isso é informação útil contra
expectativas irrealistas sobre centralização.

**E é grande em termos fiscais.** O R² de 0,909 é quase todo devido aos
efeitos fixos de item (os três medicamentos têm níveis de preço muito
distintos) — não confundir com poder explicativo da escala. Ainda assim, 14%
sobre o volume da base equivale a milhões de reais, e a dispersão da
Pergunta 1 mostra que muitos entes pagam bem mais que 14% acima do melhor
preço.

**O caso dos consórcios é o mais informativo.** Eles combinam as duas coisas:
volume alto *e* preço 20% abaixo da mediana — mais do que os −14% previstos
por β para o volume que praticam. Isso sugere que o consórcio traz algo além
da escala pura: capacidade técnica de licitação, atratividade para o
fornecedor, poder de barganha. É uma hipótese que a base não permite testar,
mas que aponta o caminho.

### Limitações — a mais importante da análise
- **Isto é associação, não causalidade.** A quantidade é *escolhida* pelo
  comprador, e compradores grandes diferem de pequenos em dimensões não
  observadas: capacidade técnica, poder de barganha, atratividade logística
  para o fornecedor, previsibilidade de demanda. **β é o gradiente
  observado, não o retorno de centralizar.** Estimar o efeito causal exigiria
  variação exógena no tamanho da compra (mudança de regra, criação de
  consórcio com data conhecida) e desenho de diferenças em diferenças.
- **Seleção pelo lado do fornecedor.** Lotes grandes atraem distribuidores
  maiores, com estrutura de custo diferente. Parte de β é composição de
  fornecedor, não desconto de volume.
- **Forma funcional imposta.** A especificação log-log assume elasticidade
  constante. Os quintis sugerem que o ganho se achata no topo — plausível,
  já que há um piso de custo de produção.
- **Efeito de escala não é gratuito.** Agregação implica custo de
  coordenação, risco de concentração de fornecedor (Pergunta 3) e perda de
  autonomia local. A análise mede o preço, não o bem-estar.
""")

md(r"""
## Pergunta 3 — O procedimento de contratação está associado ao preço? E quem fornece?

### Relevância
A dispensa de licitação é a **exceção legal** (Lei 14.133/2021, art. 75),
prevista para baixo valor e urgência. Se o preço pago por dispensa for
sistematicamente maior para um bem idêntico, o uso recorrente da exceção tem
custo mensurável — e a taxa de dispensa por ente passa a ser um indicador de
risco **acionável**, no espírito da literatura de *red flags* em compras
públicas (Fazekas & Kocsis, 2020; OCDE, 2016). Complementarmente, a
concentração de fornecedores mede dependência: quanto mais concentrado o
fornecimento, maior o risco de desabastecimento e menor a pressão
competitiva sobre o preço.

### Método
**Preço por modalidade:** teste de Mann-Whitney-Wilcoxon por medicamento —
não paramétrico, adequado a distribuições assimétricas e a n muito desiguais
entre grupos. Tamanho de efeito pela **probabilidade de superioridade**
(estatística A de Vargha-Delaney): a chance de uma dispensa sorteada ser mais
cara que um pregão sorteado. Como dispensas são, por construção legal,
compras pequenas — e compras pequenas já são mais caras pela Pergunta 2 —
o teste bruto **não basta**: usamos também o coeficiente de `modalidade` na
regressão log-log, que controla item, ano, esfera, sistema de preços **e
quantidade**.

**Concentração:** índice de **Herfindahl-Hirschman** (HHI) sobre participação
em valor por **raiz de CNPJ** (grupo econômico), por medicamento. Faixas de
referência das diretrizes antitruste (DOJ/FTC; CADE): < 1.500 desconcentrado,
1.500–2.500 moderadamente concentrado, > 2.500 concentrado.
""")

code(r"""
r3 = analise.p3_procedimento_e_preco(dfp, df)
print("Teste bruto — preço por modalidade (dispensa > pregão?):")
display(r3["testes"].style.format({
    "mediana_pregao":"R$ {:.3f}","mediana_dispensa":"R$ {:.3f}",
    "sobrepreco_%":"{:+.1f}%","p_valor":"{:.2e}","prob_superioridade":"{:.3f}"}).hide(axis="index"))
display(Image(str(r3["figuras"][0])))
""")

code(r"""
m = r2["modelo_ampliado"]
coef = m.params["C(modalidade)[T.6]"]
ic = m.conf_int().loc["C(modalidade)[T.6]"]
print("Modelo com controles (item, ano, esfera, sistema de preços, log-quantidade),")
print("erros-padrão agrupados por UASG:\n")
print(f"Efeito da dispensa sobre o preço : {100*(np.exp(coef)-1):+.1f}%")
print(f"IC 95%                           : [{100*(np.exp(ic.iloc[0])-1):+.1f}%, {100*(np.exp(ic.iloc[1])-1):+.1f}%]")
print(f"p-valor                          : {m.pvalues['C(modalidade)[T.6]']:.2e}")
print(f"\nElasticidade de escala no mesmo modelo: {m.params['logQuantidade']:+.4f}")
""")

code(r"""
print("Concentração de fornecedores por medicamento (raiz de CNPJ, participação em valor):")
display(r3["hhi"].style.format({"HHI":"{:,.0f}","CR1_%":"{:.1f}%","CR4_%":"{:.1f}%"}).hide(axis="index"))
display(Image(str(r3["figuras"][1])))
""")

code(r"""
print("Entes com maior recurso à dispensa (≥3 itens na base):")
display(r3["dispensa_por_ente"].head(10).style.format({
    "valor":"R$ {:,.2f}","taxa_dispensa_pct":"{:.1f}%"}))
""")

md(r"""
### Resultados

**Preço por modalidade — diferença bruta:**

| Medicamento | n pregão | n dispensa | mediana pregão | mediana dispensa | diferença | p |
|---|---|---|---|---|---|---|
| AAS 100 mg | 807 | 22 | R$ 0,050 | R$ 0,085 | **+70%** | 8,8×10⁻¹⁰ |
| Ácido Fólico 5 mg | 788 | 11 | R$ 0,040 | R$ 0,060 | **+50%** | 0,035 |
| Aciclovir 200 mg | 810 | 17 | R$ 0,200 | R$ 0,240 | **+20%** | 0,045 |

No AAS, a probabilidade de superioridade é **0,86**: sorteando uma dispensa e
um pregão, a dispensa é mais cara em 86% dos casos.

**Com controles** — incluindo quantidade, que é o principal confundidor — a
dispensa continua **+18% mais cara** (IC 95%, p < 10⁻⁵).

**Concentração:** HHI de **371** (Ácido Fólico) a **1.093** (Aciclovir); todos
na faixa *desconcentrado*, com 268 a 288 grupos econômicos por medicamento.
O líder do Aciclovir detém 26,5% do valor.

### Interpretação

**O achado da modalidade é o mais robusto do relatório.** A diferença bruta
poderia ser inteiramente explicada por escala — dispensas são pequenas por
definição legal, e a Pergunta 2 mostrou que pequeno é mais caro. Mas o
controle por log-quantidade **não elimina o efeito**: sobram 18%. Ou seja,
contratar sem competição custa mais do que contratar em volume pequeno com
competição.

Isso é exatamente o que a teoria de leilões prevê, e tem duas leituras
práticas:

1. **A taxa de dispensa é um indicador de risco com base empírica**, não
   apenas de conformidade formal. É o que fundamenta o indicador IND-03.
2. **Onde a dispensa é usada por falha de planejamento** — para medicamentos
   de uso contínuo e demanda previsível, como os três desta base — o custo é
   mensurável. AAS e Ácido Fólico não são compras de emergência.

**A concentração, ao contrário, é uma boa notícia.** Com HHI abaixo de 1.500
e quase 300 grupos econômicos por medicamento, o mercado de genéricos de
baixo custo é competitivo. Se houvesse concentração alta, a dispersão da
Pergunta 1 teria uma explicação de mercado; não há. **Isso reforça a
conclusão da Pergunta 1:** a dispersão de preços não vem de falta de
concorrência na oferta — vem de heterogeneidade na capacidade de compra do
lado do comprador. Que é um problema muito mais tratável.

Vale notar que o HHI cai ao longo dos anos (de 5.921 em 2021 para ~1.000-1.500
em 2024-2025 no AAS) — mas 2021 tem apenas 53 itens, e a queda é
provavelmente artefato de tamanho de amostra, não abertura de mercado.

### Limitações
- **Assimetria extrema de n.** 11 a 22 dispensas contra ~800 pregões. O
  Mann-Whitney tolera desbalanceamento, mas a precisão das medianas de
  dispensa é baixa e os p-valores de Ácido Fólico e Aciclovir estão perto do
  limiar convencional. O resultado agregado (com controles, n = 2.455) é o
  estimativo confiável; o por-item é sugestivo.
- **A decodificação da modalidade é hipótese** (seção 2.6). Se 6 não for
  dispensa, a interpretação muda — embora a *existência* de diferença de
  preço entre procedimentos permaneça.
- **Não distingue o fundamento legal** invocado (art. 75, I a XVIII). Parte
  das dispensas é legítima: emergência sanitária, desabastecimento, licitação
  deserta. O indicador sinaliza, não acusa.
- **Seleção não observada.** Entes que recorrem à dispensa podem ser
  sistematicamente diferentes (menor capacidade administrativa), e essa
  diferença — não o procedimento em si — poderia gerar o preço maior.
- **HHI mede as compras observadas, não o mercado.** Licitantes derrotados não
  aparecem na base. E a raiz de CNPJ não captura grupos econômicos com raízes
  distintas — exigiria base de controle societário (QSA/Receita Federal).
""")

md(r"""
## Análise complementar — evolução temporal
""")

code(r"""
r4 = analise.p4_serie_temporal(dfp)
display(r4["serie"].style.format("R$ {:.4f}"))
display(Image(str(r4["figuras"][0])))
print("\nItens por trimestre (base para avaliar a estabilidade das medianas):")
print(r4["n_por_trimestre"].to_string())
""")

md(r"""
### Interpretação

Os três medicamentos mostram o mesmo padrão: **alta até 2023, queda a partir
de 2024**. O coeficiente de ano no modelo com controles confirma —
2022: +9,8%, 2023: +5,4%, 2024: −0,6%, 2025: −11,7% (base 2021).

**Estes são preços nominais.** Com IPCA acumulado de ~15-18% entre 2022 e
2025, um preço nominal estável significa **queda real de dois dígitos**. A
leitura correta é que os preços destes genéricos caíram substancialmente em
termos reais — consistente com a maturidade do mercado e com o aumento do
número de fornecedores observado no HHI.

**Limitações:** (a) sem deflator, a decomposição real/nominal é aproximada —
integrar o IPCA via API SIDRA/IBGE resolveria; (b) o último trimestre tem n
pequeno (a base termina em jul/2025) e sua mediana é instável; (c) a queda no
volume de 2025 (439 itens contra ~700/ano) é compatível tanto com um recorte
que termina em julho quanto com defasagem de registro na fonte — toda leitura
de tendência recente é provisória.
""")

# ============================================================== ETAPA 5
md(r"""
---
# Etapa 5 — Indicadores

Quatro indicadores, especificados integralmente em `src/indicadores.py`
(nome, objetivo, fórmula, variáveis, granularidade, periodicidade e
limitações no docstring de cada função).

**Critérios de projeto comuns:**

1. **Robustez** — nenhuma fórmula pode ser dominada por um registro errado.
   Todas usam mediana/quantis, nunca média, e operam sobre o escopo
   comparável.
2. **Comparabilidade** — o denominador é sempre um benchmark do **mesmo item,
   no mesmo período**. Preço de medicamento não é comparável entre moléculas
   nem entre anos.
3. **Estabilidade sob coleta incremental** — o indicador de um período
   fechado não deve mudar quando o período seguinte chega. Onde isso é
   impossível (a fonte retifica retroativamente), o indicador é versionado
   pela data de extração.
4. **Acionabilidade** — cada um aponta um ente, um item ou um mercado
   específico, não só um agregado nacional.

A escolha da **mediana** como preço de referência não é arbitrária: é o
parâmetro previsto na IN SEGES/ME nº 65/2021, art. 6º, que admite mediana
quando há valores discrepantes na pesquisa de preços. Isso torna o indicador
legível pelo próprio gestor público — ele reconhece a régua.
""")

code(r"""
ind = indicadores.calcular_todos(df, dfp, r2["efeitos"]["elasticidade"])
""")

md(r"""
## IND-01 — Índice de Preço Relativo (IPR)

**Objetivo:** medir, de forma comparável entre medicamentos e períodos, se um
ente comprou acima ou abaixo do preço praticado no país para o mesmo produto.

**Fórmula:** `IPR(i) = preço(i) / mediana{preço | mesmo CATMAT, mesma unidade
de fornecimento, mesmo período}`. Agregado do ente = mediana dos IPR dos seus
itens. Grupos de referência com menos de 10 observações são suprimidos.

**Granularidade:** item (nativa); agregável a UASG, órgão, município, UF,
esfera. **Periodicidade:** trimestral recomendada (mensal é viável, mas o n
por medicamento fica pequeno e a mediana instável).

**Leitura:** 1,00 = preço típico; 1,30 = 30% acima.
""")

code(r"""
print("IPR por UF:")
display(ind["IND01_por_uf"].head(12).style.format({"IPR_mediano":"{:.3f}","IPR_p75":"{:.3f}","valor_total":"R$ {:,.0f}"}))
print("\nEntes com maior IPR mediano (≥5 itens):")
display(ind["IND01_por_ente"].head(10).style.format({"IPR_mediano":"{:.2f}","IPR_p75":"{:.2f}","valor_total":"R$ {:,.2f}"}))
""")

md(r"""
### Como ler este resultado — e por que ele exige o IND-02

O topo da lista é dominado por **hospitais e unidades militares** (Grupamento
de Apoio de Belém, Hospital Naval de Belém, hospitais de guarnição) com IPR
de 1,5 a 2,2 — mas com valor total de **centenas a poucos milhares de reais**.

Essa é a limitação central do IPR isolado, e ela é instrutiva: essas
unidades compram **quantidades pequenas**, e a Pergunta 2 mostrou que compras
pequenas são legitimamente mais caras. Publicar esse ranking como "quem paga
mais caro" seria **injusto e tecnicamente errado** — o IPR está medindo
escala, não gestão.

É exatamente para isso que existe o IND-02.
""")

md(r"""
## IND-02 — Índice de Preço Ajustado por Escala (IPAE)

**Objetivo:** separar sobrepreço de efeito de escala. Compara o ente com o
preço esperado para uma compra **do mesmo tamanho**.

**Fórmula:**
`preço_esperado(i) = mediana_item_período × (q(i)/q_mediana)^β`, com β
estimado na Etapa 4 (−0,064); `IPAE(i) = preço(i) / preço_esperado(i)`.

**Granularidade:** item; agregável a ente, município, UF.
**Periodicidade:** trimestral, com β reestimado anualmente.
""")

code(r"""
print("Entes com maior IPAE mediano (≥5 itens) — já descontado o efeito de escala:")
display(ind["IND02_por_ente"].head(12).style.format({"IPAE_mediano":"{:.2f}","excesso_ajustado":"R$ {:,.2f}"}))

print("\nComparação das duas réguas para os mesmos entes:")
comp = (ind["IND01_por_ente"][["n_itens","IPR_mediano"]]
        .join(ind["IND02_por_ente"][["IPAE_mediano","excesso_ajustado"]], how="inner")
        .sort_values("excesso_ajustado", ascending=False).head(10))
display(comp.style.format({"IPR_mediano":"{:.2f}","IPAE_mediano":"{:.2f}","excesso_ajustado":"R$ {:,.2f}"}))
""")

md(r"""
### O contraste é o resultado

Ordenando por **excesso em reais** — e não por índice — a lista muda
completamente de natureza: saem as unidades militares que compram centenas de
comprimidos e entram entes cujo desvio de preço, multiplicado pelo volume,
representa dinheiro material.

**É essa a lista que um produto de transparência deve publicar.** Um índice
alto sobre R$ 900 é uma curiosidade; um índice moderado sobre milhões de
comprimidos é política pública.

**Limitações do IPAE — importantes e não elimináveis:**
- β é **associação, não causalidade** (Pergunta 2). O ajuste remove o
  gradiente observado, não o "efeito escala verdadeiro".
- β é estimado **da própria base**, gerando dependência circular. Mitigável
  estimando β em janela anterior à de aplicação — o que é natural na coleta
  recorrente.
- **Forma funcional imposta** (potência), com elasticidade constante.
- Não captura diferenças de qualidade, prazo de entrega ou custo logístico
  regional. Um município amazônico remoto pode pagar mais por razões
  legítimas que a base não observa.
""")

md(r"""
## IND-03 — Taxa de Contratação por Dispensa (TCD)

**Objetivo:** monitorar o uso da exceção legal à licitação. A dispensa é
prevista para baixo valor e urgência; uso recorrente para medicamentos de uso
contínuo e demanda previsível sinaliza falha de planejamento — e, pela
Pergunta 3, está associado a preço 18% maior.

**Fórmula:** duas versões reportadas juntas — `TCD_itens` (itens por dispensa
/ total) e `TCD_valor` (valor por dispensa / total). **Divergência grande
entre as duas indica dispensas concentradas em poucos itens de alto valor, o
que é mais grave** — e é por isso que as duas versões existem.

**Granularidade:** UASG / órgão / município / UF / esfera.
**Periodicidade:** mensal ou trimestral (indicador de contagem, estável).
""")

code(r"""
display(ind["IND03"].head(12).style.format({
    "valor_total":"R$ {:,.2f}","valor_dispensa":"R$ {:,.2f}",
    "TCD_itens_pct":"{:.1f}%","TCD_valor_pct":"{:.1f}%"}))

print("\nAgregado por esfera:")
d3 = df.assign(_d=df.modalidade.eq("6"))
display(d3.groupby("esferaDesc").agg(
    itens=("_d","size"), dispensas=("_d","sum"),
    TCD_itens_pct=("_d", lambda s: 100*s.mean())).style.format({"TCD_itens_pct":"{:.2f}%"}))
""")

md(r"""**Limitações:** (a) a decodificação `modalidade = 6 → dispensa` é
**hipótese** (seção 2.6) e deve ser confirmada na tabela de domínio da API
antes de publicação; (b) parte das dispensas é legítima e o indicador não
distingue o fundamento legal invocado (art. 75, I a XVIII) — sinaliza, não
acusa; (c) a base cobre uma classe CATMAT, logo a taxa não representa o
perfil geral de compras do ente.
""")

md(r"""
## IND-04 — HHI de Fornecimento

**Objetivo:** medir dependência do poder público em relação a poucos
fornecedores para um mesmo medicamento. Concentração alta eleva risco de
desabastecimento e reduz pressão competitiva sobre o preço.

**Fórmula:** `HHI = Σ s_j² × 10.000`, com `s_j` = participação da raiz de
CNPJ *j* no valor do item no período. Reportado com CR1 e CR4.

**Granularidade:** item × período (também item × UF).
**Periodicidade:** anual — o HHI trimestral fica instável com poucos contratos.
""")

code(r"""
display(ind["IND04"].style.format({
    "HHI":"{:,.0f}","CR1_pct":"{:.1f}%","CR4_pct":"{:.1f}%","valor_total":"R$ {:,.0f}"}).hide(axis="index"))
""")

md(r"""
**Leitura e advertência sobre tamanho de amostra:** 2021 tem apenas 53 itens
e HHI de 3.626-5.921 — artefato de amostra pequena, não concentração real.
Os anos de 2022 a 2025, com n adequado, ficam entre 769 e 2.218: mercado
desconcentrado a moderadamente concentrado. **Este é o tipo de instabilidade
que um indicador publicado recorrentemente precisa declarar** — daí a
periodicidade anual e o reporte do n junto ao valor.

**Limitações:** (a) mede a concentração das **compras observadas**, não do
mercado — licitantes derrotados não aparecem na base; (b) a raiz de CNPJ
agrupa filiais mas não identifica grupos econômicos com raízes distintas
(exigiria QSA/Receita Federal); (c) distribuidoras e fabricantes são tratados
no mesmo plano, embora a concentração relevante para desabastecimento esteja
na **produção**.

---
## Fontes externas que aprimorariam os indicadores

| Informação | Fonte | Chave | Ganho |
|---|---|---|---|
| Preço máximo regulado (PMVG) | CMED/ANVISA | princípio ativo + apresentação (exige de/para com CATMAT) | benchmark **exógeno** — hoje o IPR usa a mediana da própria base, que não detecta sobrepreço generalizado |
| Deflator | IPCA, API SIDRA/IBGE | mês da compra | série de preços em termos reais |
| População municipal | Estimativas IBGE | `codigoMunicipio` | quantidade *per capita*, tornando entes de portes distintos comparáveis |
| Controle societário (QSA) | Dados abertos CNPJ | `niFornecedor` | HHI por grupo econômico real |
| Sanções (CEIS/CNEP) | Portal da Transparência | `niFornecedor` | contratação de fornecedor impedido — *red flag* de alta prioridade |
| Empenho e pagamento | SIAFI / Portal da Transparência | `idCompra` | passar de valor **homologado** para valor **pago** |
""")

# ============================================================== ETAPA 6
md(r"""
---
# Etapa 6 — Reprodutibilidade

## Estrutura do repositório

```
case-transparencia-brasil/
├── README.md                     ← instalação, execução, sumário dos achados
├── requirements.txt              ← dependências com versão fixada
├── data/raw/compras-gov.csv      ← insumo, imutável
├── src/
│   ├── config.py                 ← caminhos, domínios, TODOS os limiares
│   ├── ingestao.py               ← LEITURA + contrato de schema + hash
│   ├── qualidade.py              ← DIAGNÓSTICO (26 regras, 6 dimensões)
│   ├── preparacao.py             ← TRATAMENTO (tipos, dedup, escopo)
│   ├── analise.py                ← ANÁLISE (P1, P2, P3, temporal)
│   ├── indicadores.py            ← INDICADORES (IPR, IPAE, TCD, HHI)
│   └── coleta.py                 ← esqueleto do coletor da Etapa 1 (não executado)
├── notebooks/case_compras_medicamentos.ipynb   ← este documento
├── docs/
│   ├── 01_arquitetura_coleta.md            ← Etapa 1 completa
│   ├── 02_decisoes_metodologicas.md        ← todas as decisões + referências
│   └── 03_dicionario_dados_tratado.md      ← dicionário da base tratada
├── tests/test_pipeline.py        ← testes das regras e transformações
└── outputs/                      ← figuras, relatórios CSV, HTML gerado
```

**Separação exigida pela Etapa 6** — leitura / tratamento / análise em módulos
distintos, com dependência estritamente unidirecional:

`ingestao` → `qualidade` → `preparacao` → `analise` → `indicadores`

Nenhum módulo posterior é importado por um anterior. O notebook **importa**
esse código, não o duplica: a mesma função que gera o número no relatório é a
que roda em produção. É a diferença entre uma análise que pode ser
industrializada e uma que precisa ser reescrita.

## Execução

```bash
git clone <repo> && cd case-transparencia-brasil
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

pytest -q                                        # 1. valida as regras
jupyter nbconvert --to html --execute \
    notebooks/case_compras_medicamentos.ipynb \
    --output-dir outputs                         # 2. reproduz o relatório
```

## Garantias de reprodutibilidade

| Garantia | Como |
|---|---|
| **Mesmo insumo** | SHA-256 do CSV registrado na leitura (`meta['sha256']`) |
| **Mesmo ambiente** | `requirements.txt` com versões fixadas; versões impressas na seção 0 |
| **Mesmos parâmetros** | todos os limiares em `config.py`, nenhum embutido no código |
| **Mesmo resultado** | sem aleatoriedade nas análises; `config.SEED` para eventual extensão |
| **Rastreabilidade** | log de linhagem com n por etapa (seção 3) |
| **Auditabilidade** | nada apagado — marcações `flag_*` por linha |
| **Testabilidade** | funções puras; `tests/test_pipeline.py` cobre regras e transformações |
""")

code(r"""
print("Reconciliação — do bruto ao número final:")
display(metap["linhagem"])
print(f"\nHash do insumo: {meta['sha256']}")

# Persistência dos artefatos
relatorio.to_csv(config.OUTPUTS/"relatorio_qualidade.csv", index=False)
perfil.to_csv(config.OUTPUTS/"perfil_colunas.csv", index=False)
r1["tabela"].to_csv(config.OUTPUTS/"p1_dispersao_precos.csv", index=False)
r2["por_item"].to_csv(config.OUTPUTS/"p2_elasticidade_por_item.csv", index=False)
r3["testes"].to_csv(config.OUTPUTS/"p3_modalidade_testes.csv", index=False)
ind["IND01_por_ente"].to_csv(config.OUTPUTS/"ind01_ipr_por_ente.csv")
ind["IND02_por_ente"].to_csv(config.OUTPUTS/"ind02_ipae_por_ente.csv")
ind["IND03"].to_csv(config.OUTPUTS/"ind03_taxa_dispensa.csv")
ind["IND04"].to_csv(config.OUTPUTS/"ind04_hhi.csv", index=False)
# Parquet preserva tipos (datas com fuso, Int64 nulável); CSV.gz é o fallback
# universal, para que a base tratada seja legível sem dependência extra.
try:
    df.to_parquet(config.DATA_PROCESSED/"itens_compra_tratado.parquet", index=False)
    formato = "parquet"
except ImportError:
    formato = "csv.gz"
df.to_csv(config.DATA_PROCESSED/"itens_compra_tratado.csv.gz", index=False, compression="gzip")

print("\nArtefatos gravados em outputs/:")
for p in sorted(config.OUTPUTS.glob("*.csv")):
    print(f"  {p.name}")
print(f"\nBase tratada: data/processed/itens_compra_tratado.{formato} + .csv.gz"
      f"  ({len(df):,} linhas x {df.shape[1]} colunas)")
""")

md(r"""
---
## Conclusão

**Sobre a qualidade dos dados.** A base é estruturalmente sólida e
semanticamente frágil — e é a segunda parte que importa. Nenhuma ferramenta
automática de perfilamento sinalizaria problema aqui: não há célula vazia,
não há duplicata, não há falha de conversão. Os problemas que de fato
inviabilizariam a análise só aparecem quando se pergunta **o que o dado
significa**: que a ausência está gravada como texto em três formatos
diferentes — um deles um espaço, invisível a olho nu —, que o preço se refere
a unidades de fornecimento diferentes, que o valor do lote foi lançado no campo
de preço unitário, que a mesma empresa aparece com nomes diferentes, e que o
campo `marca` frequentemente não contém marca.

**Sobre os resultados.** Os três achados convergem para uma leitura única. O
preço do mesmo comprimido varia por um fator de 2 entre compradores, e ~90%
dessa variação está **dentro da mesma UF**. O mercado fornecedor é
**competitivo** (HHI < 1.500, quase 300 grupos por medicamento), então a
dispersão não vem de falta de concorrência na oferta. Há **economia de escala
real mas modesta** (−14% ao multiplicar o volume por 10), e o procedimento
importa: **dispensa custa 18% mais que pregão** para o mesmo item, mesmo
controlando quantidade.

Junto, isso desenha um problema do lado do **comprador**, não do vendedor:
heterogeneidade de capacidade de compra entre entes vizinhos, num mercado
onde o preço competitivo existe e é conhecido. É um diagnóstico otimista, no
sentido de que aponta remédios tratáveis — informação de preço acessível ao
gestor, agregação via consórcio, redução do uso da dispensa para itens de
demanda previsível — em vez de exigir mudança de estrutura de mercado.

**Sobre o que não se pode afirmar.** Nada aqui é causal. Nada aqui se
generaliza para além de três genéricos de baixo custo. E todos os valores
financeiros são **homologados, não pagos** — a integração com dados de
empenho (SIAFI) é o próximo passo mais valioso, e o único que permitiria
falar de gasto efetivo.
""")

nb["cells"] = C
nb.metadata = {
    "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
    "language_info": {"name": "python", "version": "3.12"},
}
nbf.write(nb, "notebooks/case_compras_medicamentos.ipynb")
print(f"Notebook criado com {len(C)} células")
