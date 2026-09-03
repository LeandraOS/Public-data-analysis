"""
qualidade.py — Camada de DIAGNÓSTICO de qualidade de dados (Etapa 2).

Arcabouço teórico
-----------------
A avaliação é organizada em dimensões de qualidade, seguindo a tradição
iniciada por Wang & Strong (1996) e consolidada em Batini & Scannapieco
(2016) e no DAMA-DMBOK (2ª ed., cap. 13). Usamos seis dimensões
mensuráveis sobre a base:

1. COMPLETUDE   — proporção de valores presentes (Redman, 1996).
2. UNICIDADE    — ausência de duplicidade em relação à granularidade declarada.
3. VALIDADE     — conformidade sintática/de domínio (o valor é um valor possível?).
4. CONSISTÊNCIA — coerência entre campos do mesmo registro e entre registros
                  (dependências funcionais e integridade referencial).
5. ACURÁCIA     — proximidade com o valor do mundo real. Não observável
                  diretamente sem uma fonte de verdade; aproximada aqui por
                  plausibilidade estatística e por regras de negócio.
6. ATUALIDADE   — defasagem entre o fato e seu registro (timeliness/currency).

Duas escolhas de projeto importantes:

- O diagnóstico é SEPARADO do tratamento. Este módulo apenas *mede e
  sinaliza*; nada é corrigido aqui. Quem decide o que fazer é `preparacao.py`,
  e a decisão fica documentada. Isso evita o antipadrão de "limpeza
  silenciosa", em que o número final não pode ser explicado.
- As regras são declarativas (uma função que devolve máscara booleana por
  linha), no espírito de suítes de expectativa (Great Expectations) e de
  testes de dados em dbt. Cada regra vira uma linha de relatório com
  contagem e taxa, e a marcação por linha fica disponível para auditoria.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pandas as pd

from . import config

# ==========================================================================
# Utilitários de normalização (usados tanto no diagnóstico quanto na preparação)
# ==========================================================================


def para_numero_br(serie: pd.Series) -> pd.Series:
    """Converte texto no padrão numérico pt-BR ('1.234.567,89') em float.

    A ordem das substituições importa: primeiro remove-se o separador de
    milhar ('.'), depois troca-se a vírgula decimal por ponto. Fazer o
    inverso corromperia o valor.
    """
    return pd.to_numeric(
        serie.astype("string")
        .str.strip()
        .str.replace(".", "", regex=False)
        .str.replace(",", ".", regex=False),
        errors="coerce",
    )


def normalizar_texto(serie: pd.Series) -> pd.Series:
    """Normalização canônica de texto para comparação e deduplicação.

    Pipeline: maiúsculas -> remoção de diacríticos (NFKD) -> remoção de
    pontuação -> colapso de espaços. É a etapa de *standardization* clássica
    de record linkage (Fellegi & Sunter, 1969; Christen, 2012): duas grafias
    do mesmo nome só podem ser reconhecidas como iguais depois de reduzidas
    a uma forma canônica.
    """
    s = serie.astype("string").str.upper().str.strip()
    s = s.map(
        lambda x: (
            unicodedata.normalize("NFKD", x).encode("ascii", "ignore").decode("ascii")
            if pd.notna(x)
            else x
        )
    )
    s = s.str.replace(r"[^A-Z0-9 ]+", " ", regex=True).str.replace(r"\s+", " ", regex=True)
    return s.str.strip()


def marcar_nulos(df: pd.DataFrame) -> pd.DataFrame:
    """Substitui as sentinelas textuais de ausência por pd.NA.

    Sem esta etapa, a completude medida é ilusória: a base não tem *nenhuma*
    célula vazia, mas tem milhares de "NA" literais.
    """
    out = df.copy()
    for c in out.columns:
        if out[c].dtype == object or str(out[c].dtype) in ("string", "str"):
            s = out[c].astype("string").str.strip()
            out[c] = s.mask(s.isin(config.SENTINELAS_NULAS))
    return out


# ==========================================================================
# Perfilamento (profiling)
# ==========================================================================


def perfilar_colunas(df_bruto: pd.DataFrame) -> pd.DataFrame:
    """Perfil coluna a coluna: completude, cardinalidade e valor modal.

    Distingue três estados de ausência, porque eles têm causas diferentes e
    exigem tratamentos diferentes:
      - vazio        : célula sem conteúdo no arquivo;
      - 'NA' literal : ausência declarada pela API;
      - preenchido   : valor efetivo.
    """
    df_nulo = marcar_nulos(df_bruto)
    n = len(df_bruto)
    linhas = []
    for c in df_bruto.columns:
        bruto = df_bruto[c].astype("string")
        na_literal = int((bruto.str.strip() == "NA").sum())
        vazio = int((bruto.str.strip() == "").sum())
        preenchido = int(df_nulo[c].notna().sum())
        vc = df_nulo[c].value_counts()
        linhas.append(
            {
                "coluna": c,
                "tipo_logico": config.SCHEMA_ESPERADO.get(c, "?"),
                "preenchidos": preenchido,
                "completude_%": round(100 * preenchido / n, 2),
                "na_literal": na_literal,
                "vazio": vazio,
                "distintos": int(df_nulo[c].nunique(dropna=True)),
                "cardinalidade_%": round(100 * df_nulo[c].nunique(dropna=True) / n, 2),
                "valor_modal": (str(vc.index[0])[:40] if len(vc) else None),
                "freq_modal_%": (round(100 * vc.iloc[0] / n, 2) if len(vc) else None),
            }
        )
    return pd.DataFrame(linhas)


def perfilar_numericas(df_bruto: pd.DataFrame) -> pd.DataFrame:
    """Estatísticas descritivas robustas das colunas numéricas.

    Reporta mediana e MAD ao lado de média e desvio-padrão. Em presença de
    outliers extremos — que esta base tem — média e desvio-padrão têm ponto
    de ruptura 0 (um único registro os desloca arbitrariamente), enquanto a
    mediana tem ponto de ruptura 50% (Rousseeuw & Croux, 1993). Comparar as
    duas famílias de estatística é, por si, um diagnóstico de contaminação.
    """
    linhas = []
    for c in config.COLUNAS_NUMERICAS_BR:
        s = para_numero_br(df_bruto[c]).replace(0, np.nan) if c == "codigoMunicipio" else para_numero_br(df_bruto[c])
        s = s.dropna()
        if s.empty:
            continue
        mad = float(np.median(np.abs(s - s.median())))
        linhas.append(
            {
                "coluna": c,
                "n": len(s),
                "falhas_parsing": int(para_numero_br(df_bruto[c]).isna().sum()),
                "min": s.min(),
                "p25": s.quantile(0.25),
                "mediana": s.median(),
                "p75": s.quantile(0.75),
                "p99": s.quantile(0.99),
                "max": s.max(),
                "media": s.mean(),
                "desvio_padrao": s.std(),
                "mad": mad,
                "assimetria": s.skew(),
                "razao_max_mediana": (s.max() / s.median()) if s.median() else np.nan,
            }
        )
    return pd.DataFrame(linhas)


# ==========================================================================
# Motor de regras
# ==========================================================================


@dataclass
class Regra:
    """Uma verificação de qualidade declarativa.

    `func` recebe o DataFrame e devolve uma máscara booleana em que True
    marca VIOLAÇÃO da regra. `severidade` orienta a resposta operacional:
      - 'bloqueante' : inviabiliza a análise se ocorrer;
      - 'alta'       : afeta resultados; exige tratamento explícito;
      - 'media'      : afeta subconjuntos ou interpretações;
      - 'informativa': documenta característica da fonte, sem ação.
    """

    id: str
    dimensao: str
    descricao: str
    func: Callable[[pd.DataFrame], pd.Series]
    severidade: str = "media"
    acao: str = ""
    tags: list[str] = field(default_factory=list)


def _mz_score(x: pd.Series) -> pd.Series:
    """Escore-z modificado de Iglewicz & Hoaglin (1993): 0,6745*(x-med)/MAD.

    A constante 0,6745 calibra o MAD para que o escore seja comparável ao
    z-score gaussiano. Ao contrário do z-score clássico, não usa média nem
    desvio-padrão, e portanto não é ele mesmo distorcido pelos outliers que
    deveria detectar (problema de *masking*).
    """
    med = x.median()
    mad = np.median(np.abs(x - med))
    if not mad or np.isnan(mad):
        return pd.Series(0.0, index=x.index)
    return 0.6745 * (x - med) / mad


def construir_regras() -> list[Regra]:
    """Catálogo de regras aplicado à base. Cada regra é rastreável e testável."""

    def _num(df, c):
        return para_numero_br(df[c])

    R = []

    # ---------------- COMPLETUDE ----------------
    R.append(Regra(
        "COMP-01", "Completude",
        "nomeUnidadeFornecimento ausente ('NA') — impede saber a que se refere o preço",
        lambda df: df["nomeUnidadeFornecimento"].str.strip().eq("NA"),
        "alta", "Registro mantido, mas excluído do escopo de comparação de preços.",
    ))
    R.append(Regra(
        "COMP-02", "Completude",
        "esfera ausente ('NA') — impede recorte por nível de governo",
        lambda df: df["esfera"].str.strip().eq("NA"),
        "media", "Mantido como categoria 'Não informado'; não imputado.",
    ))
    R.append(Regra(
        "COMP-03", "Completude",
        "municipio ausente ('NA') — impede recorte territorial fino",
        lambda df: df["municipio"].str.strip().eq("NA"),
        "media", "Mantido; UF permanece utilizável.",
    ))
    R.append(Regra(
        "COMP-04", "Completude",
        "criterioJulgamento sem conteúdo (célula contém apenas espaço)",
        lambda df: df["criterioJulgamento"].str.strip().eq(""),
        "informativa", "Ausência estruturalmente associada à modalidade 6 (ver CONS-04).",
    ))
    R.append(Regra(
        "COMP-05", "Completude",
        "coluna integralmente vazia (nomeUnidadeMedida)",
        lambda df: df["nomeUnidadeMedida"].str.strip().eq("NA"),
        "informativa", "Coluna descartada na base tratada: nenhuma informação.",
    ))

    # ---------------- UNICIDADE ----------------
    R.append(Regra(
        "UNIC-01", "Unicidade",
        "linha inteiramente duplicada",
        lambda df: df.duplicated(keep=False),
        "bloqueante", "Nenhuma ocorrência; nada a fazer.",
    ))
    R.append(Regra(
        "UNIC-02", "Unicidade",
        "chave de negócio (idCompra, numeroItemCompra) repetida com idItemCompra distinto",
        lambda df: df.duplicated(["idCompra", "numeroItemCompra"], keep=False),
        "alta", "Mantido apenas o registro de dataHoraAtualizacaoItem mais recente (SCD tipo 1).",
    ))
    R.append(Regra(
        "UNIC-03", "Unicidade",
        "idItemCompra repetido (chave técnica deveria ser única)",
        lambda df: df.duplicated(["idItemCompra"], keep=False),
        "bloqueante", "Nenhuma ocorrência: idItemCompra é chave primária válida.",
    ))

    # ---------------- VALIDADE ----------------
    R.append(Regra(
        "VALD-01", "Validade",
        "precoUnitario não conversível ou não positivo",
        lambda df: _num(df, "precoUnitario").isna() | (_num(df, "precoUnitario") <= 0),
        "bloqueante", "Nenhuma ocorrência.",
    ))
    R.append(Regra(
        "VALD-02", "Validade",
        "quantidade não conversível, não positiva ou fracionária",
        lambda df: (
            _num(df, "quantidade").isna()
            | (_num(df, "quantidade") <= 0)
            | (_num(df, "quantidade") % 1 != 0)
        ),
        "bloqueante", "Nenhuma ocorrência.",
    ))
    R.append(Regra(
        "VALD-03", "Validade",
        "CNPJ do fornecedor sem 14 dígitos ou com dígito verificador inválido",
        lambda df: ~df["niFornecedor"].map(cnpj_valido),
        "alta", "Sinalizado; CNPJ inválido impede vínculo confiável com bases externas.",
    ))
    R.append(Regra(
        "VALD-04", "Validade",
        "codigoMunicipio fora do padrão IBGE de 7 dígitos",
        lambda df: ~codigo_ibge(df["codigoMunicipio"]).str.len().eq(7).fillna(False),
        "media", "Sinalizado; corresponde exatamente às linhas com municipio ausente.",
    ))
    R.append(Regra(
        "VALD-05", "Validade",
        "valor fora do domínio conhecido em campo categórico",
        lambda df: (
            ~df["forma"].isin(config.DOM_FORMA)
            | ~df["modalidade"].isin(config.DOM_MODALIDADE)
            | ~df["estado"].isin(set(config.UF_POR_PREFIXO_IBGE.values()))
        ),
        "alta", "Nenhuma ocorrência; domínios estáveis no período.",
    ))
    R.append(Regra(
        "VALD-06", "Validade",
        "marca com conteúdo não identificador (genérico, unidade, resíduo de HTML)",
        lambda df: marca_nao_informativa(df["marca"]),
        "alta", "Marca não usada como dimensão analítica; apenas descrita.",
    ))

    R.append(Regra(
        "VALD-07", "Validade",
        "valor com espaço em branco de preenchimento (padding) — quebra comparação exata",
        lambda df: padding_em_branco(df),
        "alta", "Todas as colunas de texto sofrem strip na tipagem, antes de qualquer comparação.",
    ))

    # ---------------- CONSISTÊNCIA ----------------
    R.append(Regra(
        "CONS-01", "Consistência",
        "mesmo CNPJ associado a mais de uma razão social",
        lambda df: df["niFornecedor"].isin(
            (g := df.groupby("niFornecedor")["nomeFornecedor"].nunique())[g > 1].index
        ),
        "alta", "Fornecedor identificado por CNPJ, não por nome; nome canônico = mais recente.",
    ))
    R.append(Regra(
        "CONS-02", "Consistência",
        "mesma razão social associada a mais de um CNPJ",
        lambda df: df["nomeFornecedor"].isin(
            (g := df.groupby("nomeFornecedor")["niFornecedor"].nunique())[g > 1].index
        ),
        "informativa", "Esperado (matriz/filiais); tratado por raiz de CNPJ quando pertinente.",
    ))
    R.append(Regra(
        "CONS-03", "Consistência",
        "UF divergente do prefixo do código IBGE do município",
        lambda df: divergencia_uf_ibge(df),
        "alta", "Nenhuma divergência: integridade territorial confirmada.",
    ))
    R.append(Regra(
        "CONS-04", "Consistência",
        "combinação modalidade x criterioJulgamento fora do padrão observado",
        lambda df: ~(
            (df["modalidade"].eq("5") & df["criterioJulgamento"].str.strip().isin(["V", "D"]))
            | (df["modalidade"].eq("6") & df["criterioJulgamento"].str.strip().isin(["", "1"]))
        ),
        "informativa", "Dependência funcional perfeita; base da decodificação dos domínios.",
    ))
    R.append(Regra(
        "CONS-05", "Consistência",
        "criterioJulgamento='D' sem desconto, ou desconto>0 sem criterio='D'",
        lambda df: df["criterioJulgamento"].str.strip().eq("D") ^ (_num(df, "percentualMaiorDesconto") > 0),
        "informativa", "Coerência perfeita; confirma 'D' = maior desconto.",
    ))
    R.append(Regra(
        "CONS-06", "Consistência",
        "dataResultado anterior à dataCompra",
        lambda df: pd.to_datetime(df["dataResultado"], utc=True, errors="coerce")
        < pd.to_datetime(df["dataCompra"], utc=True, errors="coerce"),
        "media", "Sinalizado; datas não usadas como sequência causal, apenas como referência temporal.",
    ))
    R.append(Regra(
        "CONS-07", "Consistência",
        "atualização do item anterior à data da compra (violação de ordem lógica)",
        lambda df: pd.to_datetime(df["dataHoraAtualizacaoItem"], utc=True, errors="coerce")
        < pd.to_datetime(df["dataCompra"], utc=True, errors="coerce"),
        "media", "Sinalizado; indica retificação retroativa ou carga histórica.",
    ))
    R.append(Regra(
        "CONS-08", "Consistência",
        "forma farmacêutica da unidade de fornecimento incompatível com a descrição CATMAT",
        lambda df: df["descricaoItem"].str.contains("DOSAGEM", na=False)
        & df["nomeUnidadeFornecimento"].isin(["BISNAGA", "FRASCO", "FRASCO-AMPOLA", "SACHÊ"]),
        "alta", "Excluído do escopo de comparação de preços por não comparabilidade.",
    ))

    # ---------------- ACURÁCIA (plausibilidade) ----------------
    R.append(Regra(
        "ACUR-01", "Acurácia",
        "preço unitário implausível: |escore-z modificado| > 3,5 em log(preço), por item",
        lambda df: preco_outlier(df),
        "alta", "Excluído das estatísticas de preço; analisado separadamente como erro de registro.",
    ))
    R.append(Regra(
        "ACUR-02", "Acurácia",
        "padrão 'valor do lote no campo de preço unitário': quantidade=1 e preço >> mediana do item",
        lambda df: padrao_lote_no_preco(df),
        "alta", "Excluído; erro de preenchimento identificável por assinatura conjunta.",
    ))
    R.append(Regra(
        "ACUR-03", "Acurácia",
        "capacidadeUnidadeFornecimento = 0 (valor impossível para uma capacidade)",
        lambda df: _num(df, "capacidadeUnidadeFornecimento").eq(0),
        "informativa", "Interpretado como 'não informado' e não como zero; coluna não usada nas análises.",
    ))

    # ---------------- ATUALIDADE ----------------
    R.append(Regra(
        "ATUAL-01", "Atualidade",
        "defasagem entre a compra e sua última atualização superior a 365 dias",
        lambda df: (
            pd.to_datetime(df["dataHoraAtualizacaoItem"], utc=True, errors="coerce")
            - pd.to_datetime(df["dataCompra"], utc=True, errors="coerce")
        ).dt.days
        > 365,
        "informativa", "Documentado: registros antigos continuam sendo retificados na fonte.",
    ))

    return R


# ---------------- funções auxiliares das regras ----------------


def cnpj_valido(cnpj) -> bool:
    """Verifica os dois dígitos verificadores do CNPJ (módulo 11).

    Validar o DV é mais forte que checar o comprimento: detecta erro de
    digitação e valor inventado, e é pré-requisito para integrar a base com
    cadastros externos (Receita Federal, CEIS, CNEP).
    """
    if not isinstance(cnpj, str):
        return False
    d = re.sub(r"\D", "", cnpj).zfill(14)
    if len(d) != 14 or len(set(d)) == 1:
        return False
    for tamanho, pesos in ((12, [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]),
                           (13, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])):
        soma = sum(int(d[i]) * pesos[i] for i in range(tamanho))
        resto = soma % 11
        dv = 0 if resto < 2 else 11 - resto
        if int(d[tamanho]) != dv:
            return False
    return True


PADRAO_MARCA_NAO_INFORMATIVA = re.compile(
    r"^(?:NA|N/A|-+|\.+|\?+|X+)$"
    r"|GENERIC|GENÉRIC"
    r"|SIMILAR"
    r"|CONFORME"
    r"|^COMPRIMIDO$|^CAPSULA$|^CÁPSULA$|^UN$|^CP$|^CO$|^UNIDADE$"
    r"|SEM MARCA|A DEFINIR|QUALQUER|NACIONAL$"
    r"|CMED|ANVISA"
    r"|JAVASCRI|<|>|HTTP",
    re.IGNORECASE,
)


def marca_nao_informativa(serie: pd.Series) -> pd.Series:
    """Marca registros cujo campo `marca` não identifica um laboratório.

    O campo mistura três coisas: marca comercial de fato, texto de edital
    ('CONFORME TR', 'GENÉRICO'), e ruído de extração ('BRASTERAPICAjavascri' —
    resíduo de HTML/JS, indício de que a origem do dado envolveu raspagem de
    tela em algum ponto da cadeia).
    """
    s = serie.astype("string").str.strip()
    return s.isna() | s.str.len().le(2) | s.str.contains(PADRAO_MARCA_NAO_INFORMATIVA, na=False)


def codigo_ibge(serie: pd.Series) -> pd.Series:
    """Reconstitui o código IBGE de 7 dígitos a partir do texto corrompido.

    A fonte entrega o código já formatado como número decimal pt-BR
    ('4.108.403,00') — sintoma clássico de passagem por planilha entre a API
    e o arquivo final. Recuperamos a parte inteira e validamos o comprimento.
    """
    n = para_numero_br(serie)
    return n.round(0).astype("Int64").astype("string")


def padding_em_branco(df: pd.DataFrame) -> pd.Series:
    """Marca linhas em que algum campo de texto tem espaço à esquerda/direita.

    Problema silencioso e traiçoeiro: `criterioJulgamento` guarda `' '` (um
    espaço), não `''`. Qualquer comparação exata — `== ""`, `isin([""])`,
    um `GROUP BY`, um `JOIN` — trata `' '` e `''` como valores diferentes.
    O efeito é uma categoria fantasma que não aparece em nenhuma inspeção
    visual, porque espaço e vazio são graficamente idênticos.

    Este diagnóstico foi acrescentado depois de um teste de contrato falhar:
    a regra CONS-04 acusava 74 violações que o cruzamento de frequências não
    mostrava. A divergência era exatamente esta.
    """
    colunas_texto = [c for c, t in config.SCHEMA_ESPERADO.items()
                     if t in ("texto", "categoria")]
    mask = pd.Series(False, index=df.index)
    for c in colunas_texto:
        if c in df:
            s = df[c].astype("string")
            mask |= (s != s.str.strip()).fillna(False)
    return mask


def divergencia_uf_ibge(df: pd.DataFrame) -> pd.Series:
    codigo = codigo_ibge(df["codigoMunicipio"])
    prefixo = codigo.str[:2].map(config.UF_POR_PREFIXO_IBGE)
    return prefixo.notna() & (prefixo != df["estado"])


def escopo_comparavel(df: pd.DataFrame) -> pd.Series:
    """Máscara do subconjunto em que preços unitários são comparáveis entre si."""
    return df["nomeUnidadeFornecimento"].isin(config.UNIDADES_COMPARAVEIS)


def preco_outlier(df: pd.DataFrame) -> pd.Series:
    """|escore-z modificado| > 3,5 sobre log(preço), estratificado por item CATMAT.

    A estratificação é essencial: os três medicamentos têm níveis de preço
    diferentes (o Aciclovir custa ~4x o AAS). Um limiar global classificaria
    todo o Aciclovir como outlier. Detecção de anomalia sem condicionar pelo
    grupo correto mede heterogeneidade, não anomalia.
    """
    preco = para_numero_br(df["precoUnitario"])
    log_preco = np.log(preco.where(preco > 0))
    mz = log_preco.groupby(df["codigoItemCatalogo"], observed=True).transform(_mz_score)
    return mz.abs() > config.LIMIAR_MZ


def padrao_lote_no_preco(df: pd.DataFrame) -> pd.Series:
    """Assinatura conjunta do erro 'valor total do lote lançado como preço unitário'.

    Nenhum dos dois sinais isolados é conclusivo — comprar 1 unidade é
    legítimo, e um preço alto pode ser um item caro. A conjunção é que
    identifica o erro: quantidade = 1 *e* preço unitário ordens de magnitude
    acima da mediana do mesmo medicamento.
    """
    preco = para_numero_br(df["precoUnitario"])
    qtd = para_numero_br(df["quantidade"])
    mediana_item = preco.groupby(df["codigoItemCatalogo"], observed=True).transform("median")
    return qtd.le(config.QTD_SUSPEITA_LOTE) & preco.gt(100 * mediana_item)


# ==========================================================================
# Execução do motor
# ==========================================================================


def avaliar(df_bruto: pd.DataFrame, regras: list[Regra] | None = None):
    """Aplica todas as regras e devolve (relatório agregado, marcações por linha)."""
    regras = regras or construir_regras()
    n = len(df_bruto)
    marcas, linhas = {}, []

    for r in regras:
        try:
            mask = r.func(df_bruto).fillna(False).astype(bool)
        except Exception as exc:  # a falha de uma regra não derruba o diagnóstico
            linhas.append({"id": r.id, "dimensao": r.dimensao, "descricao": r.descricao,
                           "severidade": r.severidade, "violacoes": None,
                           "taxa_%": None, "acao": f"ERRO NA REGRA: {exc}"})
            continue
        marcas[r.id] = mask
        linhas.append({
            "id": r.id, "dimensao": r.dimensao, "descricao": r.descricao,
            "severidade": r.severidade, "violacoes": int(mask.sum()),
            "taxa_%": round(100 * mask.sum() / n, 3), "acao": r.acao,
        })

    relatorio = pd.DataFrame(linhas)
    marcacoes = pd.DataFrame(marcas, index=df_bruto.index)
    return relatorio, marcacoes


def indice_qualidade(relatorio: pd.DataFrame) -> pd.DataFrame:
    """Agrega as taxas de violação por dimensão.

    Advertência metodológica: este é um resumo de comunicação, não uma
    medida com significado absoluto. Colapsar dimensões em um número único
    exige pesos arbitrários, e regras com severidades distintas não são
    comensuráveis. Reportamos, portanto, por dimensão, e sempre ao lado da
    tabela completa de regras.
    """
    d = relatorio.dropna(subset=["taxa_%"])
    return (
        d.groupby("dimensao")
        .agg(regras=("id", "count"),
             regras_violadas=("violacoes", lambda s: int((s > 0).sum())),
             pior_taxa_pct=("taxa_%", "max"))
        .sort_values("pior_taxa_pct", ascending=False)
        .reset_index()
    )
