# Decisões metodológicas

Registro de todas as escolhas que afetam os números do relatório, com
justificativa e efeito. A regra que orientou o conjunto: **nenhuma linha é
apagada da base**. Registros problemáticos recebem marcação (`flag_*`) e uma
classificação de escopo; as exclusões acontecem no ponto de uso, por filtro
explícito. Assim qualquer número é reconciliável com as 2.706 linhas
originais, e qualquer decisão pode ser revertida mudando um parâmetro em
`src/config.py`.

---

## Em linguagem direta

Este documento justifica cada escolha técnica. Se você só quiser saber **o que
foi decidido** e **por quê**, são estas sete decisões:

| Decisão | Em uma frase | Por quê |
|---|---|---|
| **Nada foi apagado** | registros problemáticos ganharam etiqueta, não foram removidos | qualquer número é rastreável até a regra que o incluiu ou excluiu, e qualquer decisão pode ser revertida |
| **Ler tudo como texto** | nenhum tipo é adivinhado na leitura | senão o programa decide sozinho, e em silêncio, o que é vazio — e foi assim que quase perdi um problema real |
| **Fornecedor é CNPJ, não nome** | a mesma empresa aparecia com até três razões sociais | contar por nome inflaria o número de fornecedores e esconderia a concentração de mercado |
| **Estatística robusta, não média** | usamos mediana e MAD | um único registro de R$ 253 mil por comprimido bastaria para distorcer qualquer média |
| **Preço só se compara na mesma embalagem** | análise restrita a comprimido e cápsula | comparar bisnaga com comprimido é comparar embalagem, não medicamento |
| **Nada foi imputado** | onde falta informação, o relatório diz "não informado" | preencher um vazio com estimativa cria um número inventado com aparência de número medido |
| **Sem correção de inflação** | trabalhamos com valores nominais e dizemos isso | escolher um deflator para três genéricos exigiria fundamentação que não temos; a limitação declarada é mais honesta que a precisão aparente |

**A decisão mais importante é a primeira.** É ela que faz a diferença entre
"confie no meu número" e "aqui está como você mesmo verifica o meu número" —
que, numa organização cujo produto é a confiabilidade do dado público, é a
diferença que importa.

---

## 1. Granularidade e chaves

**Granularidade declarada:** uma linha = **um item de uma compra pública**
(`idItemCompra`), na classe CATMAT 6505, restrita a três medicamentos.

Declarar o grão antes de tudo é o primeiro passo da modelagem dimensional
(Kimball): sem ele, não existe agregação correta, porque não se sabe o que
está sendo contado.

| Chave | Natureza | Situação |
|---|---|---|
| `idItemCompra` | técnica (surrogate da fonte) | única — 2.706/2.706. É a PK |
| `(idCompra, numeroItemCompra)` | de negócio | **3 pares duplicados** |
| `idCompra` | agrupadora | 1.578 compras, 1,71 itens/compra (máx. 7) |

Dimensões implícitas, todas em relação N:1 com o fato: fornecedor
(`niFornecedor`), unidade gestora (`codigoUasg`), órgão (`codigoOrgao`),
município (`codigoMunicipio`), item de catálogo (`codigoItemCatalogo`),
tempo (`dataCompra`). A base é uma **tabela-fato desnormalizada** — cada
linha repete todos os atributos de todas as dimensões.

**Verificação de integridade das dimensões:**
- `codigoUasg → nomeUasg`: dependência funcional perfeita (0 violações);
- `codigoMunicipio → estado`: 100% consistente com o prefixo IBGE de UF;
- `niFornecedor → nomeFornecedor`: **violada** — 48 CNPJs com mais de uma
  razão social (ver §4).

---

## 2. Leitura como texto, tipagem depois

**Decisão:** ler todo o CSV com `dtype=str, keep_default_na=False`; converter
tipos só na camada de tratamento.

**Por quê:** três problemas concretos desta base seriam mascarados pela
inferência automática de tipos.

1. `keep_default_na=False` — a fonte grava a **string literal `"NA"`** como
   sentinela de ausência. Com o comportamento padrão, o pandas a converteria
   em `NaN` antes de qualquer contagem, e a distinção entre *ausência
   declarada pela API* e *célula vazia no arquivo* se perderia. Sem esta
   opção, a base parece 100% completa: não há nenhuma célula vazia, mas há
   2.706 `"NA"` em uma única coluna.
2. `dtype=str` em identificadores — `niFornecedor`, `codigoUasg` e
   `codigoMunicipio` são **rótulos, não grandezas**. Convertidos para inteiro,
   perderiam zeros à esquerda (fatal para CNPJ) e passariam a admitir
   operações sem sentido (média de CNPJ).
3. `dtype=str` em `modalidade` — inferido como inteiro, quebraria o *join*
   com a tabela de domínio, que é textual.

---

## 3. Números em formato brasileiro

`quantidade`, `precoUnitario`, `percentualMaiorDesconto`,
`capacidadeUnidadeFornecimento` e `codigoMunicipio` vêm no padrão pt-BR
(`"40.000,00"`). Conversão: remover o separador de milhar, depois trocar a
vírgula decimal por ponto — nessa ordem (o inverso corromperia o valor).

**Resultado:** 0 falhas de conversão em 2.706 × 5 células. O formato é
consistente em toda a base.

**`codigoMunicipio` é caso à parte:** chega como `"4.108.403,00"`, isto é, o
código IBGE de 7 dígitos formatado como *número decimal*. Isso não é um
formato de API — é assinatura de passagem por planilha entre a fonte e o
arquivo. Reconstituímos o código a partir da parte inteira e validamos o
comprimento (7 dígitos) e o prefixo de UF. O achado importa além da
correção: indica que a cadeia de produção do arquivo tem um passo manual, e
um processo automatizado (Etapa 1) deve consumir a API diretamente.

---

## 4. Identidade do fornecedor: CNPJ, não nome

**Problema:** 526 CNPJs distintos, 560 razões sociais. 48 CNPJs aparecem com
mais de uma grafia:

```
01578276000114 → 'ASLI COMERCIAL EIRELI'      | 'ASLI COMERCIAL LTDA'
02814497000700 → 'CIMED INDUSTRIA S.A.'       | 'CIMED INDUSTRIA DE MEDICAMENTOS LTDA'
06106005000180 → 'STOCK MED PRODUTOS MEDICO-HOSPITALARES LTDA.' | 'STOCK MED S.A'
05377160000178 → 'DENTAL ALENCAR IMPORTACAO E EXPORTACAO COMERCIO E REPRE' | (nome completo)
```

Três causas distintas, todas visíveis nos exemplos: mudança de tipo societário
(a extinção da EIRELI pela Lei 14.195/2021 converteu automaticamente milhares
de empresas em LTDA), alteração de razão social, e **truncamento do campo** no
registro mais antigo.

**Decisão:** a identidade é o CNPJ. O nome canônico é a grafia do registro
mais recente daquele CNPJ — regra determinística e reproduzível, preferível a
"a mais frequente" (que empata em vários casos) ou "a mais longa" (arbitrária,
e ainda pode ser a errada).

**Decisão complementar — raiz de CNPJ:** 526 CNPJs correspondem a 511 raízes
(8 primeiros dígitos), ou seja, 15 pares matriz/filial. Análises de
**concentração de mercado usam a raiz** (o grupo econômico é o agente
relevante); análises de **contratação usam o CNPJ completo** (o
estabelecimento é quem contrata).

**Limitação declarada:** a raiz não identifica grupos econômicos com raízes
distintas. Fazê-lo exigiria base de controle societário (QSA da Receita
Federal) — ver §11.

**O que NÃO foi feito, e por quê:** não aplicamos deduplicação difusa
(*fuzzy matching*) sobre nomes. Com o CNPJ disponível e validado, casamento
probabilístico (Fellegi & Sunter, 1969) só adicionaria falsos positivos:
"CIRURGICA SANTA CRUZ" e "CIRURGICA SANTA CRUZ COM. DE PRODUTOS
HOSPITALARES" podem ser a mesma empresa ou duas empresas diferentes, e o
CNPJ resolve isso sem inferência.

---

## 5. Decodificação de campos não documentados

O dicionário fornecido marca `criterioJulgamento` como "NA" e não descreve os
códigos de `modalidade`. Em vez de descartar os campos ou aceitar um palpite,
inferimos a semântica por **evidência interna**, e reportamos como hipótese.

**Evidência 1 — dependência funcional perfeita entre `modalidade` e
`criterioJulgamento`** (0 exceções em 2.706 linhas):

| modalidade | criterioJulgamento | n |
|---|---|---|
| 5 | `V` | 2.603 |
| 5 | `D` | 10 |
| 6 | *(vazio)* | 74 |
| 6 | `1` | 19 |

**Evidência 2 — `criterioJulgamento = 'D'` ⟺ `percentualMaiorDesconto > 0`**,
com coerência de 10/10 em ambas as direções. Nenhum registro tem desconto sem
o critério `D`, e nenhum critério `D` tem desconto zero.

**Inferência:** `D` = *maior desconto*; `V` = *menor preço/valor*. A
modalidade 5 é a que tem critério de julgamento (procedimento competitivo) e a
6 não tem (o campo fica vazio ou recebe um marcador de "não aplicável").
Combinando com a distribuição (96,6% na modalidade 5, o que é esperado para
medicamentos sob a Lei 14.133/2021) e com o achado de preço da Etapa 4
(modalidade 6 é 18% mais caro *controlando* item, ano, esfera e quantidade —
exatamente o previsto pela teoria para contratação sem competição), a leitura
mais provável é **5 = Pregão, 6 = Dispensa de licitação**.

**Status:** hipótese sustentada por três evidências independentes e
convergentes, **não** fato confirmado. Registrada como hipótese em
`config.DOM_MODALIDADE`, sinalizada em toda a apresentação e listada como
limitação do indicador IND-03. Antes de publicação, deve ser confirmada
contra a tabela de domínio da API.

---

## 6. Comparabilidade de preços: a decisão mais consequente

`precoUnitario` é o preço por **unidade de fornecimento** — e a unidade
varia dentro do mesmo medicamento:

| nomeUnidadeFornecimento | n | preço mediano |
|---|---|---|
| COMPRIMIDO | 2.592 | R$ 0,06 |
| CÁPSULA | 30 | R$ 0,05 |
| BISNAGA | 13 | R$ 2,40 |
| FRASCO-AMPOLA | 10 | R$ 1,55 |
| FRASCO | 3 | R$ 0,24 |
| SACHÊ | 1 | R$ 0,03 |
| *ausente* (`"NA"`) | 57 | R$ 0,05 |

**Comparar R$ 2,40 (bisnaga) com R$ 0,06 (comprimido) não é comparar preço —
é comparar embalagens.** E há um problema adicional: a descrição CATMAT dos
três itens especifica dosagem oral ("ACICLOVIR, DOSAGEM: 200 MG"), o que é
**inconsistente** com bisnaga e frasco-ampola (pomada e injetável). Ou o item
foi classificado no CATMAT errado, ou a unidade de fornecimento foi preenchida
errada. Nos dois casos, o registro não é comparável (regra `CONS-08`).

**Decisão:** estatísticas de preço restritas às unidades COMPRIMIDO e CÁPSULA
— formas sólidas orais em que 1 unidade de fornecimento = 1 dose. Os 27
registros de outras formas e os 57 sem unidade informada permanecem na base e
são usados nas análises que não dependem de preço (contagem, cobertura
territorial, concentração de fornecedores).

**Efeito:** o escopo de preços contém 2.455 dos 2.703 registros (90,8%).

---

## 7. Valores extremos: três diagnósticos diferentes

Os preços têm assimetria extrema: o AAS 100 mg tem mediana de R$ 0,05 e
máximo de **R$ 253.300,00** — 5 milhões de vezes a mediana. Tratar isso como
"outlier estatístico" a ser removido seria perder o diagnóstico. Investigando,
há três fenômenos distintos:

### 7.1 Valor do lote lançado no campo de preço unitário

Os 15 registros com `quantidade = 1` têm preço mediano de **R$ 2.673,77**,
contra R$ 0,06 nos 2.691 restantes. Os quatro maiores:

| preço unitário | quantidade | comprador |
|---|---|---|
| R$ 253.300,00 | 1 | Pref. Mun. de Guarulhos - SP |
| R$ 205.000,00 | 1 | Pref. Mun. de Alhandra - PB |
| R$ 200.000,00 | 1 | Pref. Mun. de Alhandra - PB |
| R$ 182.000,00 | 1 | Pref. Mun. de Alhandra - PB |

**Diagnóstico:** o operador lançou o valor total do lote no campo de preço
unitário e "1" na quantidade. É erro de preenchimento, não preço.

O ponto metodológico: **nenhum dos dois sinais isolados é conclusivo.**
Comprar 1 unidade é legítimo; um preço alto pode ser um item caro. É a
*conjunção* — quantidade 1 **e** preço >100× a mediana do mesmo CATMAT — que
identifica o erro. Regra `ACUR-02`.

### 7.2 Preços implausíveis sem assinatura clara

**Método:** escore-z modificado (Iglewicz & Hoaglin, 1993),
`0,6745·(x − mediana)/MAD`, aplicado sobre **log(preço)** e **estratificado
por CATMAT**, com limiar 3,5.

Três escolhas, cada uma necessária:

- **Escore modificado, não z-score clássico.** O z-score usa média e
  desvio-padrão, ambos com ponto de ruptura 0: um único registro de
  R$ 253.300 desloca a média e infla o desvio-padrão o suficiente para o
  próprio outlier deixar de parecer extremo — o fenômeno de *masking*. A
  mediana e o MAD têm ponto de ruptura 50% (Rousseeuw & Croux, 1993).
- **Em log.** A distribuição de preços é assimétrica à direita e o processo
  gerador é multiplicativo (margens, descontos e escala agem
  proporcionalmente). Em nível, o limiar simétrico rejeitaria muitos preços
  altos legítimos e nenhum preço baixo suspeito.
- **Estratificado por item.** O Aciclovir custa ~4× o AAS (medianas de R$ 0,20
  e R$ 0,05). Um limiar global classificaria todo o Aciclovir como outlier:
  mediria heterogeneidade entre produtos, não anomalia dentro de um produto.

**Resultado:** 160 registros (6,6% do escopo comparável) sinalizados.

**Decisão:** excluídos das *estatísticas de preço*, mantidos na base com
marcação. Não são "lixo" — são um achado por si (§7.1 mostra que uma parte é
erro identificável) e devem entrar em qualquer indicador de qualidade do dado
que a organização publique.

### 7.3 Semântica divergente: critério "maior desconto"

Nos 10 registros com `criterioJulgamento = 'D'`, `precoUnitario` e
`percentualMaiorDesconto` são inconsistentes entre si: há preço de R$ 1,15
com 82,61% de desconto, e R$ 0,19 com 84%. A leitura mais provável é que,
nesse critério, `precoUnitario` seja o preço **de referência do edital**, não
o preço final homologado.

**Decisão:** classificados em escopo próprio (`criterio_desconto`) e excluídos
das estatísticas de preço — não por serem implausíveis, mas por **medirem
outra coisa**. Confundir preço de referência com preço pago enviesaria o
resultado para cima.

### 7.4 Valores extremos de quantidade: mantidos

A maior quantidade é 71 milhões de comprimidos de AAS, pelo Consórcio
Intergestores Paraná Saúde. Estatisticamente é um outlier; substantivamente é
exatamente o que um consórcio de compras existe para fazer, e o preço
associado (R$ 0,03) é coerente com a economia de escala estimada. **Nenhum
valor de quantidade foi excluído**: são valores extremos verdadeiros, não
erros. A análise usa log(quantidade), que acomoda a escala.

---

## 8. Duplicidade: versões, não cópias

Três pares violam a chave de negócio `(idCompra, numeroItemCompra)`. Exemplo:

| idItemCompra | numeroItem | quantidade | preço | fornecedor | atualização |
|---|---|---|---|---|---|
| 4106059 | 7 | 107.280 | 0,04 | TOP NORTE | 2024-12-06 |
| 4447432 | 7 | **1.072.800** | 0,05 | NOVASUL | 2025-02-21 |

Mesma compra, mesmo item, `idItemCompra` diferentes, **fornecedor diferente e
quantidade 10× diferente**. Não são cópias: são duas **versões** do mesmo
registro no tempo. O registro foi retificado na origem e a extração preservou
ambas.

**Decisão:** manter a versão mais recente por `dataHoraAtualizacaoItem` — SCD
tipo 1, na terminologia de Kimball. Contar as duas versões inflaria valor e
contagem de itens. As três versões antigas são devolvidas em
`meta['versoes_antigas']`, não descartadas.

**Consequência para a Etapa 1:** este é o achado que determina a estratégia de
coleta. A fonte é mutável retroativamente, logo o coletor precisa (a) usar
`dataHoraAtualizacaoItem` como campo de controle e (b) versionar o histórico
(SCD tipo 2), para que a retificação seja auditável em vez de silenciosa.

---

## 9. Ausências: por mecanismo, nunca imputadas

Todas as ausências desta base são **sentinelas textuais `"NA"`**, não células
vazias. Classificação por mecanismo (Rubin, 1976; Little & Rubin, 2019), que
é o que determina o tratamento:

| Coluna | `"NA"` | Mecanismo | Decisão |
|---|---|---|---|
| `nomeUnidadeMedida` | 2.706 (100%) | estrutural — campo nunca populado | coluna descartada |
| `siglaUnidadeMedida` | 2.689 (99,4%) | estrutural | não usada |
| `nomeUnidadeFornecimento` | 57 (2,1%) | **MNAR** — concentra-se em esfera federal (34 de 57) | mantido; excluído do escopo de preço |
| `esfera` | 57 (2,1%) | MNAR — inclui Senado Federal | categoria "Não informado" |
| `municipio` | 9 (0,3%) | aparentemente MCAR | mantido; UF permanece utilizável |
| `criterioJulgamento` | 74 vazios | **MAR condicionado** a `modalidade = 6` | preservado como informação |

**Nenhum valor foi imputado.** Justificativa: (a) as taxas são baixas e não
comprometem poder estatístico; (b) para as variáveis centrais — preço e
quantidade — não há ausência alguma; (c) imputar `esfera` ou unidade de
fornecimento criaria valor sem base, e num produto de transparência o custo
de publicar um número inventado é maior que o de publicar um "não informado".
A ausência de `criterioJulgamento` é, ela própria, **informação**: sinaliza a
modalidade (§5).

---

## 10. Padronização e o campo `marca`

`marca` tem 501 valores distintos que caem em 380 após normalização canônica
(maiúsculas → remoção de diacríticos → remoção de pontuação → colapso de
espaços). Mas o problema real não é ortográfico: **11,6% dos registros
(314) não contêm marca alguma.** O campo mistura três coisas:

1. marca comercial de fato — `HIPOLABOR`, `NATULAB`, `PRATI DONADUZZI`;
2. texto de edital — `GENERICO` (127 registros somando variantes de grafia),
   `COMPRIMIDO` (105), `CONFORME TR`, `SIMILAR`, `A DEFINIR`, `CMED/ANVISA`;
3. **ruído de extração** — `BRASTERAPICAjavascri`, resíduo de HTML/JavaScript.

O item 3 é o mais relevante para a Etapa 1: indica que o dado passou por
**raspagem de tela** em algum ponto da cadeia, e reforça a decisão de
consumir a API diretamente e preservar o payload bruto.

**Decisão:** `marca` **não é usada como dimensão analítica**. Normalizada e
marcada (`marcaInformativa`), é descrita como problema de qualidade, não
usada para agrupar. Qualquer análise "por laboratório" sobre este campo
produziria uma categoria fantasma "GENÉRICO" com 127 registros, competindo com
laboratórios reais.

---

## 11. Fontes externas que aprimorariam a análise

| Informação | Fonte | Chave de integração | Ganho |
|---|---|---|---|
| Preço máximo regulado (PMVG/CMED) | CMED/ANVISA | princípio ativo + apresentação (exige de/para com CATMAT) | benchmark **exógeno**: hoje o benchmark é a mediana da própria base, que não detecta sobrepreço generalizado |
| Deflator de preços | IPCA/IPCA-saúde, API SIDRA/IBGE | mês da compra | separar variação real de nominal na série temporal (§ Etapa 4) |
| População do município | Estimativas IBGE | `codigoMunicipio` | quantidade *per capita*, tornando entes de portes distintos comparáveis |
| Controle societário (QSA) | Dados abertos CNPJ / Receita Federal | `niFornecedor` | grupos econômicos com raízes distintas; HHI mais fiel (§4) |
| Sanções (CEIS/CNEP) | Portal da Transparência | `niFornecedor` | contratação de fornecedor impedido — *red flag* de alta prioridade |
| Cobertura assistencial | DATASUS/SIA-SIH, CNES | `codigoMunicipio` | relacionar volume comprado a necessidade epidemiológica |
| Empenho e pagamento efetivo | SIAFI / Portal da Transparência | `idCompra` | passar de valor **homologado** para valor **pago**, resolvendo a limitação central da §12 |

---

## 12. Limitações que atravessam toda a análise

1. **Valor homologado ≠ valor pago.** `quantidade × precoUnitario` é o valor
   registrado, não o desembolsado. Em SISRP (registro de preços — 88,7% da
   base), a ata registra preço e quantidade *máxima*, e o empenho posterior
   pode ser parcial ou nulo. Todos os valores financeiros deste relatório são
   **valores contratados/registrados**, e assim são reportados.
2. **Recorte de três medicamentos.** A base cobre uma classe CATMAT (6505) e,
   dentro dela, três moléculas de baixo custo e alto volume, todas genéricas.
   Nada aqui se generaliza para medicamentos de alto custo, biológicos ou
   sob patente, onde a estrutura de mercado é radicalmente diferente.
3. **Cobertura desconhecida.** Não sabemos se a base é o universo das compras
   desses itens no período ou uma amostra. A queda no volume de 2025 (439
   itens contra ~700/ano nos anos anteriores) é compatível com um recorte que
   termina em julho de 2025, mas também com defasagem de registro na fonte.
   Toda leitura de tendência recente é, por isso, provisória.
4. **Sem contrafactual.** Não há informação sobre licitantes derrotados,
   número de propostas ou preço de referência do edital (exceto nos 10
   registros com critério de desconto). Não é possível medir intensidade
   competitiva diretamente, apenas o resultado.
5. **Associação, não causalidade.** As três análises da Etapa 4 são
   descritivas e comparativas. Em particular, a elasticidade
   preço-quantidade (§Etapa 4, P2) é um gradiente observado, não o retorno
   de centralizar compras: compradores grandes diferem de pequenos em
   dimensões não observadas (capacidade técnica, poder de barganha,
   atratividade logística para o fornecedor).
6. **Preços nominais.** Sem deflator, a série temporal mistura variação real
   e inflação. Integrar o IPCA (§11) resolveria.

---

## Referências

> **Nota:** as referências abaixo são as obras de base da metodologia
> empregada. Recomenda-se conferir a edição e a paginação antes de citar
> formalmente.

**Qualidade de dados**
- Wang, R. Y.; Strong, D. M. (1996). *Beyond Accuracy: What Data Quality Means to Data Consumers*. Journal of Management Information Systems, 12(4).
- Batini, C.; Scannapieco, M. (2016). *Data and Information Quality: Dimensions, Principles and Techniques*. Springer.
- Redman, T. C. (1996). *Data Quality for the Information Age*. Artech House.
- DAMA International (2017). *DAMA-DMBOK: Data Management Body of Knowledge*, 2ª ed., cap. 13.

**Estatística robusta e detecção de anomalias**
- Tukey, J. W. (1977). *Exploratory Data Analysis*. Addison-Wesley.
- Iglewicz, B.; Hoaglin, D. C. (1993). *How to Detect and Handle Outliers*. ASQC Quality Press.
- Rousseeuw, P. J.; Croux, C. (1993). *Alternatives to the Median Absolute Deviation*. JASA, 88(424).
- Huber, P. J.; Ronchetti, E. M. (2009). *Robust Statistics*, 2ª ed. Wiley.

**Dados ausentes**
- Rubin, D. B. (1976). *Inference and Missing Data*. Biometrika, 63(3).
- Little, R. J. A.; Rubin, D. B. (2019). *Statistical Analysis with Missing Data*, 3ª ed. Wiley.

**Integração e modelagem**
- Fellegi, I. P.; Sunter, A. B. (1969). *A Theory for Record Linkage*. JASA, 64(328).
- Christen, P. (2012). *Data Matching*. Springer.
- Kimball, R.; Ross, M. (2013). *The Data Warehouse Toolkit*, 3ª ed. Wiley.

**Econometria**
- Moulton, B. R. (1990). *An Illustration of a Pitfall in Estimating the Effects of Aggregate Variables on Micro Units*. Review of Economics and Statistics, 72(2).
- Cameron, A. C.; Miller, D. L. (2015). *A Practitioner's Guide to Cluster-Robust Inference*. Journal of Human Resources, 50(2).

**Compras públicas**
- Bandiera, O.; Prat, A.; Valletti, T. (2009). *Active and Passive Waste in Government Spending*. American Economic Review, 99(4).
- Bajari, P.; Tadelis, S. (2001). *Incentives versus Transaction Costs: A Theory of Procurement Contracts*. RAND Journal of Economics, 32(3).
- Fazekas, M.; Kocsis, G. (2020). *Uncovering High-Level Corruption: Cross-National Objective Corruption Risk Indicators*. British Journal of Political Science, 50(1).
- OCDE (2016). *Preventing Corruption in Public Procurement*.

**Normativos brasileiros**
- Lei nº 14.133/2021 (Lei de Licitações e Contratos), arts. 23 e 75.
- Instrução Normativa SEGES/ME nº 65/2021 (pesquisa de preços), art. 6º.
- Lei nº 14.195/2021, art. 41 (transformação automática de EIRELI em sociedade limitada unipessoal).
