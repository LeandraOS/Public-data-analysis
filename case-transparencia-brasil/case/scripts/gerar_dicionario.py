import sys; sys.path.insert(0,'.')
from src import ingestao, preparacao

DESC = {
 "idCompra":("origem","Identificador da compra. 1.578 compras, 1,71 itens em média."),
 "idItemCompra":("origem","**Chave primária.** Identificador técnico do item; único."),
 "forma":("origem","Sistema de preços: SISPP (praticados) ou SISRP (registro de preços)."),
 "modalidade":("origem","Código da modalidade. `5` e `6`; leitura provável pregão/dispensa — **hipótese**, ver §5 das decisões."),
 "criterioJulgamento":("origem","`V` (menor preço) ou `D` (maior desconto) — decodificado por evidência. Nulo ⟺ modalidade 6."),
 "numeroItemCompra":("origem","Número sequencial do item na compra. Compõe a chave de negócio."),
 "descricaoItem":("origem","Descrição CATMAT. **Apenas 3 valores distintos** na base."),
 "codigoItemCatalogo":("origem","Código CATMAT: 267502 (AAS 100mg), 267503 (Ácido Fólico 5mg), 268370 (Aciclovir 200mg)."),
 "siglaUnidadeMedida":("origem","Quase integralmente ausente (99,4%). Não utilizada."),
 "nomeUnidadeFornecimento":("origem","**Crítica para comparação de preços.** COMPRIMIDO, CÁPSULA, BISNAGA, FRASCO-AMPOLA, FRASCO, SACHÊ. Ausente em 57 registros."),
 "siglaUnidadeFornecimento":("origem","Abreviação da unidade de fornecimento."),
 "capacidadeUnidadeFornecimento":("origem","99,4% igual a zero — interpretado como não informado, não como zero. Não utilizada."),
 "quantidade":("origem","Quantidade adquirida. 1 a 71 milhões. Nenhum valor excluído: extremos são legítimos."),
 "precoUnitario":("origem","Preço por **unidade de fornecimento** — só comparável dentro da mesma unidade."),
 "percentualMaiorDesconto":("origem","Maior desconto vs preço de referência. >0 apenas quando critério = `D` (10 registros)."),
 "niFornecedor":("origem","CNPJ do fornecedor. **Todos os 526 válidos** (dígito verificador módulo 11)."),
 "nomeFornecedor":("origem","Razão social como veio da fonte. 560 valores para 526 CNPJs — **não usar como identidade**."),
 "marca":("origem","Marca/laboratório. **11,6% não contém marca** — não usada como dimensão analítica."),
 "codigoUasg":("origem","Código da unidade gestora. Dependência funcional perfeita com nomeUasg."),
 "nomeUasg":("origem","Nome da unidade gestora beneficiada."),
 "codigoMunicipio":("derivada","Código IBGE de 7 dígitos, **reconstituído** do texto corrompido (`4.108.403,00`). Nulo em 9 registros (string `'nan'` na origem)."),
 "municipio":("origem","Município do ente comprador. Ausente em 9 registros."),
 "estado":("origem","UF. 27 valores; 100% consistente com o prefixo IBGE."),
 "codigoOrgao":("origem","Código do órgão responsável."),
 "nomeOrgao":("origem","Nome do órgão responsável."),
 "poder":("origem","E (Executivo), L (Legislativo), J (Judiciário). Nulo em 5."),
 "esfera":("origem","F (Federal), E (Estadual), M (Municipal). Nulo em 57."),
 "dataCompra":("origem","Data da compra, em **UTC**. dez/2021 a jul/2025."),
 "dataHoraAtualizacaoCompra":("origem","Última atualização da compra, UTC."),
 "dataHoraAtualizacaoItem":("origem","**Campo de controle da coleta incremental** (Etapa 1) e da deduplicação. UTC."),
 "dataResultado":("origem","Data da homologação. Igual a dataCompra em 99% dos casos."),
 "dataHoraAtualizacaoUasg":("origem","Última atualização do cadastro da UASG. Vai até 2010 — não é data do fato."),
 "raizCnpj":("derivada","8 primeiros dígitos do CNPJ = **grupo econômico**. 511 raízes para 526 CNPJs. Usar em análises de concentração."),
 "cnpjValido":("derivada","Resultado da validação de dígito verificador. True em 100% dos registros."),
 "fornecedorCanonico":("derivada","Razão social do registro **mais recente** do CNPJ. Regra determinística; usar esta, não `nomeFornecedor`."),
 "fornecedorNormalizado":("derivada","`fornecedorCanonico` em forma canônica (maiúsculas, sem diacríticos nem pontuação)."),
 "uasgNormalizada":("derivada","`nomeUasg` em forma canônica."),
 "marcaNormalizada":("derivada","`marca` em forma canônica. 501 valores crus → 380 normalizados."),
 "marcaInformativa":("derivada","False quando `marca` não identifica laboratório (genérico, unidade, texto de edital, resíduo de HTML)."),
 "valorTotalItem":("derivada","`quantidade × precoUnitario`. **Valor homologado, NÃO valor pago** — ver §12 das decisões."),
 "logPrecoUnitario":("derivada","log natural do preço. Base da detecção de outliers e da regressão log-log."),
 "logQuantidade":("derivada","log natural da quantidade."),
 "anoCompra":("derivada","Ano da compra. Usado como efeito fixo."),
 "mesCompra":("derivada","Ano-mês (`YYYY-MM`)."),
 "trimestreCompra":("derivada","Ano-trimestre (`YYYYQn`). Granularidade recomendada para os indicadores."),
 "diasAteAtualizacao":("derivada","Dias entre a compra e sua última atualização. Mediana ~450 dias — a fonte retifica o passado."),
 "itensNaCompra":("derivada","Nº de itens na mesma `idCompra`. 1 a 7."),
 "ehConsorcio":("derivada","True se a UASG é consórcio intermunicipal. 26 registros; pagam ~20% abaixo da mediana."),
 "formaDesc":("derivada","Rótulo legível de `forma`."),
 "modalidadeDesc":("derivada","Rótulo legível de `modalidade` — **marcado como hipótese**."),
 "criterioDesc":("derivada","Rótulo legível de `criterioJulgamento` — **marcado como hipótese**."),
 "esferaDesc":("derivada","Rótulo legível de `esfera`; ausência vira 'Não informado'."),
 "poderDesc":("derivada","Rótulo legível de `poder`."),
 "escopo_preco":("derivada","**Campo de controle mais importante.** `comparavel` (2.455) · `preco_implausivel` (160) · `unidade_divergente` (84) · `criterio_desconto` (4)."),
}

b,_ = ingestao.ler_bruto()
df,_ = preparacao.preparar(b)
n = len(df)

linhas = []
flags = []
for c in df.columns:
    dtype = str(df[c].dtype)
    preench = int(df[c].notna().sum())
    dist = int(df[c].nunique(dropna=True))
    if c.startswith("flag_"):
        flags.append((c, preench, int(df[c].sum()) if df[c].dtype == bool else dist))
        continue
    origem, desc = DESC.get(c, ("derivada", "—"))
    linhas.append(f"| `{c}` | {dtype} | {origem} | {preench:,} ({100*preench/n:.1f}%) | {dist:,} | {desc} |")

cab = """# Dicionário da base tratada

Saída de `src/preparacao.preparar()` — **2.703 linhas** (2.706 brutas menos 3
versões antigas) × colunas abaixo. Persistida em
`data/processed/itens_compra_tratado.parquet` e `.csv.gz`.

Três colunas do arquivo original foram descartadas por não carregarem
informação: `nomeUnidadeMedida` (100% ausente), `codigoClasse` e `nomeClasse`
(constantes — são o recorte da extração, não variáveis).

## Em linguagem direta — as três coisas que você precisa saber antes de usar esta base

1. **Para qualquer estatística de preço, filtre `escopo_preco == "comparavel"`.**
   Sem esse filtro você estará somando preços de bisnaga com preços de
   comprimido e incluindo registros onde o valor do lote inteiro foi lançado
   como preço unitário. São 2.455 dos 2.703 registros.
2. **`valorTotalItem` é o valor homologado, não o valor pago.** Em registro de
   preços (89% da base), a ata registra o preço e a quantidade *máxima*; o
   empenho pode ser parcial ou não ocorrer. Não use como despesa efetiva.
3. **Para identificar fornecedor, use `niFornecedor` ou `raizCnpj` — nunca
   `nomeFornecedor`.** A mesma empresa aparece na fonte com até três razões
   sociais diferentes.

Dois campos merecem cautela adicional: `modalidadeDesc` e `criterioDesc` são
**hipóteses** decodificadas por evidência interna, não domínios documentados
pela fonte. E `marca` não deve ser usada como dimensão analítica: em 11,6% dos
casos ela não contém marca alguma.

---

**Origem:** `origem` = campo da fonte, apenas tipado e com sentinelas
normalizadas · `derivada` = criado nesta análise.

| Coluna | Tipo | Origem | Preenchidos | Distintos | Descrição e advertências |
|---|---|---|---|---|---|
"""

rodape = f"""

---

## Colunas de marcação (`flag_*`)

Uma coluna booleana por regra de qualidade ({len(flags)} no total), com o
resultado da regra **por linha**. É o que torna cada exclusão auditável:
qualquer registro fora do escopo de preço pode ser rastreado até a regra
específica que o classificou.

| Coluna | Registros marcados |
|---|---|
""" + "\n".join(f"| `{c}` | {v:,} |" for c, _, v in flags) + """

Catálogo completo das regras — dimensão, severidade e ação adotada — em
`outputs/relatorio_qualidade.csv` e na seção 2.5 do relatório.

---

## Como usar a base tratada

```python
import pandas as pd
df = pd.read_parquet("data/processed/itens_compra_tratado.parquet")

# Estatísticas de preço: SEMPRE filtrar o escopo comparável
dfp = df[df.escopo_preco == "comparavel"]

# Contagens, cobertura territorial, concentração: usar a base completa
df.groupby("estado").size()

# Identidade de fornecedor: usar niFornecedor ou raizCnpj, nunca nomeFornecedor
df.groupby("raizCnpj").valorTotalItem.sum()
```

**Três advertências que valem repetir:**

1. `valorTotalItem` é valor **homologado**, não pago.
2. `precoUnitario` só é comparável **dentro da mesma unidade de fornecimento**.
3. `modalidadeDesc` e `criterioDesc` são **hipóteses** inferidas por evidência
   interna, não domínios documentados.
"""

open("docs/03_dicionario_dados_tratado.md", "w").write(cab + "\n".join(linhas) + rodape)
print("dicionário gerado:", len(linhas), "colunas +", len(flags), "flags")
