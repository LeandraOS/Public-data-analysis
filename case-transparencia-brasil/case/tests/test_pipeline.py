"""
Testes do pipeline.

Duas categorias:

1. **Testes de unidade das transformações** — usam dados sintéticos mínimos e
   verificam a lógica isoladamente. Não dependem do CSV.
2. **Testes de contrato sobre a base real** — verificam invariantes que, se
   quebrarem, indicam que a fonte mudou. Numa coleta recorrente, é este
   conjunto que roda a cada carga e dispara alerta.

Executar: `pytest -q`
"""

import numpy as np
import pandas as pd
import pytest

from src import config, ingestao, preparacao, qualidade


# ==========================================================================
# 1. Unidade — transformações
# ==========================================================================


@pytest.mark.parametrize("texto,esperado", [
    ("40.000,00", 40000.0),
    ("0,15", 0.15),
    ("1.234.567,89", 1234567.89),
    ("253.300,00", 253300.0),
    ("4.108.403,00", 4108403.0),   # codigoMunicipio corrompido por planilha
    ("", np.nan),
    ("NA", np.nan),
])
def test_parsing_numerico_br(texto, esperado):
    r = qualidade.para_numero_br(pd.Series([texto])).iloc[0]
    if np.isnan(esperado):
        assert pd.isna(r)
    else:
        assert r == pytest.approx(esperado)


def test_ordem_das_substituicoes_importa():
    """Trocar a vírgula antes de remover o ponto corromperia o valor.

    Este teste existe para travar o bug: '1.234,56' -> se trocássemos ','
    por '.' primeiro, teríamos '1.234.56', que não é número.
    """
    assert qualidade.para_numero_br(pd.Series(["1.234,56"])).iloc[0] == pytest.approx(1234.56)


@pytest.mark.parametrize("texto,esperado", [
    ("ASLI COMERCIAL EIRELI", "ASLI COMERCIAL EIRELI"),
    ("Cimed Indústria S.A.", "CIMED INDUSTRIA S A"),
    ("  espaços   duplos  ", "ESPACOS DUPLOS"),
    ("AÇÃO/PÚBLICA-LTDA.", "ACAO PUBLICA LTDA"),
])
def test_normalizacao_texto(texto, esperado):
    assert qualidade.normalizar_texto(pd.Series([texto])).iloc[0] == esperado


@pytest.mark.parametrize("cnpj,valido", [
    ("34027398000171", True),    # da base
    ("35830966000130", True),    # da base
    ("11111111111111", False),   # dígitos repetidos
    ("12345678000199", False),   # DV inválido
    ("123", False),
    (None, False),
])
def test_validacao_cnpj(cnpj, valido):
    assert qualidade.cnpj_valido(cnpj) is valido


def test_escore_z_modificado_resiste_a_masking():
    """O ponto central da escolha do escore modificado.

    Com 20 valores próximos de 1 e um de 10.000, o z-score clássico não
    detecta o outlier (ele infla o próprio desvio-padrão — masking).
    O escore modificado detecta.
    """
    np.random.seed(config.SEED)
    x = pd.Series(list(np.random.normal(1.0, 0.1, 20)) + [10_000.0])
    z_classico = abs((x - x.mean()) / x.std()).iloc[-1]
    z_modificado = abs(qualidade._mz_score(x)).iloc[-1]
    assert z_classico < 5           # não detecta: o outlier inflou o próprio sigma
    assert z_modificado > 100       # detecta


def test_marca_nao_informativa():
    s = pd.Series(["HIPOLABOR", "GENERICO", "COMPRIMIDO", "Conforme TR",
                   "BRASTERAPICAjavascri", "-", "NATULAB", "CP"])
    r = qualidade.marca_nao_informativa(s)
    assert list(r) == [False, True, True, True, True, True, False, True]


def test_padrao_lote_exige_as_duas_condicoes():
    """Nem quantidade=1 nem preço alto isolados devem disparar a regra."""
    df = pd.DataFrame({
        "precoUnitario": ["0,05", "0,05", "253.300,00", "0,10"],
        "quantidade":    ["1",    "1000", "1",          "1"],
        "codigoItemCatalogo": ["267502"] * 4,
    })
    r = qualidade.padrao_lote_no_preco(df)
    assert not r.iloc[0]   # qtd=1 com preço normal -> legítimo
    assert not r.iloc[1]   # preço normal, qtd alta -> legítimo
    assert r.iloc[2]       # qtd=1 E preço absurdo -> erro de lote
    assert not r.iloc[3]   # qtd=1, preço 2x a mediana -> não é lote


def test_deduplicacao_mantem_versao_mais_recente():
    df = pd.DataFrame({
        "idCompra": ["A", "A", "B"],
        "numeroItemCompra": [1, 1, 1],
        "idItemCompra": ["antigo", "novo", "outro"],
        "dataHoraAtualizacaoItem": pd.to_datetime(
            ["2024-01-01", "2025-01-01", "2024-06-01"], utc=True),
    })
    mantidos, removidos = preparacao.deduplicar(df)
    assert len(mantidos) == 2
    assert set(mantidos.idItemCompra) == {"novo", "outro"}
    assert list(removidos.idItemCompra) == ["antigo"]


# ==========================================================================
# 2. Contrato — invariantes da base real
# ==========================================================================


@pytest.fixture(scope="module")
def bruto():
    df, _ = ingestao.ler_bruto()
    return df


@pytest.fixture(scope="module")
def tratado(bruto):
    df, meta = preparacao.preparar(bruto)
    return df, meta


def test_contrato_de_schema(bruto):
    rel = ingestao.validar_schema(bruto)
    assert rel["colunas_ausentes"] == []
    assert rel["colunas_novas"] == []


def test_chave_primaria_unica(bruto):
    assert bruto.idItemCompra.is_unique


def test_sem_falha_de_parsing_numerico(bruto):
    """Falha de parsing só onde há sentinela de ausência declarada.

    Se esta asserção quebrar numa coleta futura, o formato numérico da fonte
    mudou (ex.: separador decimal virou ponto) — que é exatamente o cenário
    de schema drift previsto em docs/01_arquitetura_coleta.md, §7.
    """
    for c in config.COLUNAS_NUMERICAS_BR:
        sentinela = bruto[c].astype("string").str.strip().isin(config.SENTINELAS_NULAS)
        falhas = qualidade.para_numero_br(bruto[c]).isna() & ~sentinela
        assert falhas.sum() == 0, f"{c}: {falhas.sum()} falhas fora de sentinela"


def test_preco_e_quantidade_positivos(bruto):
    assert (qualidade.para_numero_br(bruto.precoUnitario) > 0).all()
    assert (qualidade.para_numero_br(bruto.quantidade) > 0).all()


def test_integridade_territorial(bruto):
    """UF sempre consistente com o prefixo do código IBGE do município."""
    assert qualidade.divergencia_uf_ibge(bruto).sum() == 0


def test_dependencia_funcional_uasg(bruto):
    assert (bruto.groupby("codigoUasg").nomeUasg.nunique() > 1).sum() == 0


def test_dependencia_modalidade_criterio(bruto):
    """Base da decodificação da seção 2.6: se quebrar, a hipótese cai."""
    crit = bruto.criterioJulgamento.str.strip()   # a fonte grava ' ', não ''
    valido = (
        (bruto.modalidade.eq("5") & crit.isin(["V", "D"]))
        | (bruto.modalidade.eq("6") & crit.isin(["", "1"]))
    )
    assert valido.all()


def test_criterio_D_equivale_a_desconto(bruto):
    desconto = qualidade.para_numero_br(bruto.percentualMaiorDesconto) > 0
    assert (bruto.criterioJulgamento.str.strip().eq("D") == desconto).all()


def test_padding_em_branco_detectado(bruto):
    """Regressão: 'criterioJulgamento' guarda ' ' e não ''.

    Foi este teste que revelou o problema — a regra CONS-04 acusava 74
    violações que o cruzamento de frequências não mostrava, porque espaço e
    vazio são graficamente idênticos.
    """
    assert qualidade.padding_em_branco(bruto).sum() == 102
    assert bruto.criterioJulgamento.eq(" ").sum() == 74


def test_dominios_categoricos_estaveis(bruto):
    assert set(bruto.forma.unique()) <= set(config.DOM_FORMA)
    assert set(bruto.modalidade.unique()) <= set(config.DOM_MODALIDADE)
    assert set(bruto.estado.unique()) <= set(config.UF_POR_PREFIXO_IBGE.values())


def test_linhagem_reconcilia(tratado):
    """Toda linha perdida no pipeline tem explicação registrada."""
    df, meta = tratado
    lin = meta["linhagem"]
    assert lin.iloc[0].n_linhas == 2706
    assert lin.iloc[-1].n_linhas == len(df)
    assert lin.iloc[0].n_linhas - len(df) == len(meta["versoes_antigas"])


def test_escopo_particiona_a_base(tratado):
    df, _ = tratado
    assert df.escopo_preco.notna().all()
    assert df.escopo_preco.value_counts().sum() == len(df)


def test_base_de_precos_e_comparavel(tratado):
    df, _ = tratado
    dfp = preparacao.base_precos(df)
    assert dfp.nomeUnidadeFornecimento.isin(config.UNIDADES_COMPARAVEIS).all()
    assert not dfp.criterioJulgamento.eq("D").any()
    assert (dfp.precoUnitario > 0).all()


def test_nenhum_registro_apagado(tratado):
    """A base tratada preserva todos os idItemCompra, exceto versões antigas."""
    df, meta = tratado
    df_bruto, _ = ingestao.ler_bruto()
    perdidos = set(df_bruto.idItemCompra) - set(df.idItemCompra)
    assert perdidos == set(meta["versoes_antigas"].idItemCompra)


def test_valor_total_coerente(tratado):
    df, _ = tratado
    assert np.allclose(df.valorTotalItem, df.quantidade * df.precoUnitario)
