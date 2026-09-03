"""
coleta.py — Esqueleto do coletor descrito em docs/01_arquitetura_coleta.md.

NÃO É EXECUTADO neste case (a Etapa 1 pede proposta, não implementação).
Está aqui porque algumas decisões da proposta só ficam inequívocas em código:
a política de retry, a retomada por página, o MERGE idempotente e o
fechamento de versão no SCD tipo 2. As dependências de infraestrutura
(cliente HTTP, object storage, banco) aparecem como interfaces abstratas.
"""

from __future__ import annotations

import json
import logging
import random
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Iterator, Protocol

log = logging.getLogger(__name__)

# ==========================================================================
# Parâmetros operacionais
# ==========================================================================

BASE_URL = "https://dadosabertos.compras.gov.br"
ENDPOINT_ITENS = "/modulo-legado/1_consultarItensCompra"  # confirmar na doc vigente
CODIGO_CLASSE_MEDICAMENTOS = 6505

MAX_TENTATIVAS = 6
ESPERA_BASE_S = 1.0
ESPERA_TETO_S = 300.0
REQ_POR_SEGUNDO = 5.0
CONCORRENCIA = 4
TIMEOUT_S = 60
DIAS_SOBREPOSICAO = 7          # folga deliberada sobre o watermark
FALHAS_PARA_ABRIR_CIRCUITO = 10

ERROS_TRANSITORIOS = {408, 425, 429, 500, 502, 503, 504}
ERROS_DEFINITIVOS = {400, 401, 403, 404, 422}


# ==========================================================================
# Interfaces de infraestrutura (injetadas — mantém o coletor testável)
# ==========================================================================


class ClienteHTTP(Protocol):
    def get(self, url: str, params: dict, timeout: int) -> "Resposta": ...


class Resposta(Protocol):
    status: int
    headers: dict
    def json(self) -> dict: ...


class Armazenamento(Protocol):
    """Object storage append-only para a camada bronze."""
    def gravar(self, chave: str, conteudo: bytes) -> str: ...
    def existe(self, chave: str) -> bool: ...


class RepositorioEstado(Protocol):
    """Persistência do watermark, dos checkpoints e dos manifestos."""
    def watermark(self, particao: str) -> datetime | None: ...
    def salvar_watermark(self, particao: str, valor: datetime) -> None: ...
    def ultima_pagina(self, run_id: str, particao: str) -> int: ...
    def salvar_checkpoint(self, run_id: str, particao: str, pagina: int) -> None: ...
    def salvar_manifesto(self, manifesto: dict) -> None: ...


# ==========================================================================
# Erros e controle de fluxo
# ==========================================================================


class ErroTransitorio(Exception):
    """Vale repetir."""


class ErroDefinitivo(Exception):
    """Não vale repetir — provável mudança de contrato ou credencial."""


class CircuitoAberto(Exception):
    """Fonte indisponível de forma persistente: encerra a execução como parcial."""


@dataclass
class Limitador:
    """Token bucket simples: limita a vazão do lado do cliente.

    Segurar a vazão preventivamente é diferente de reagir ao 429: evita
    degradar um serviço público compartilhado e reduz a chance de bloqueio.
    """
    req_por_segundo: float
    _ultimo: float = 0.0

    def aguardar(self) -> None:
        intervalo = 1.0 / self.req_por_segundo
        espera = self._ultimo + intervalo - time.monotonic()
        if espera > 0:
            time.sleep(espera)
        self._ultimo = time.monotonic()


@dataclass
class DisjuntorCircuito:
    limite: int = FALHAS_PARA_ABRIR_CIRCUITO
    falhas: int = 0

    def registrar_falha(self) -> None:
        self.falhas += 1
        if self.falhas >= self.limite:
            raise CircuitoAberto(f"{self.falhas} falhas consecutivas na fonte")

    def registrar_sucesso(self) -> None:
        self.falhas = 0


# ==========================================================================
# Requisição com política de retry
# ==========================================================================


def requisitar(cliente: ClienteHTTP, url: str, params: dict,
               limitador: Limitador, disjuntor: DisjuntorCircuito) -> dict:
    """GET com backoff exponencial e jitter completo.

    Jitter (aleatorização da espera) evita o 'thundering herd': sem ele,
    workers que falharam juntos voltam a bater na API exatamente juntos,
    reproduzindo a sobrecarga que causou a falha.
    """
    for tentativa in range(MAX_TENTATIVAS):
        limitador.aguardar()
        try:
            r = cliente.get(url, params=params, timeout=TIMEOUT_S)
            if r.status == 200:
                disjuntor.registrar_sucesso()
                return r.json()
            if r.status in ERROS_DEFINITIVOS:
                raise ErroDefinitivo(f"HTTP {r.status} em {url} params={params}")
            if r.status in ERROS_TRANSITORIOS:
                espera = float(r.headers.get("Retry-After", 0)) or None
                raise ErroTransitorio(f"HTTP {r.status}")
            raise ErroTransitorio(f"HTTP inesperado {r.status}")
        except ErroDefinitivo:
            raise
        except Exception as exc:
            disjuntor.registrar_falha()
            if tentativa == MAX_TENTATIVAS - 1:
                raise
            espera = min(ESPERA_BASE_S * 2 ** tentativa, ESPERA_TETO_S)
            espera = random.uniform(0, espera)  # full jitter
            log.warning("Tentativa %d/%d falhou (%s). Aguardando %.1fs",
                        tentativa + 1, MAX_TENTATIVAS, exc, espera)
            time.sleep(espera)
    raise ErroTransitorio("tentativas esgotadas")


# ==========================================================================
# Paginação com retomada
# ==========================================================================


def paginar(cliente, params_base: dict, estado: RepositorioEstado,
            run_id: str, particao: str, limitador, disjuntor) -> Iterator[tuple[int, dict]]:
    """Itera as páginas do endpoint, retomando do último checkpoint.

    Ordenação explícita por `idItemCompra` é o que permite paginação estável:
    com offset sobre resultado não ordenado, inserções na fonte entre duas
    requisições fazem registros serem lidos duas vezes ou nunca.
    """
    pagina = estado.ultima_pagina(run_id, particao) + 1
    total_declarado = None
    total_lido = 0

    while True:
        payload = requisitar(
            cliente, f"{BASE_URL}{ENDPOINT_ITENS}",
            {**params_base, "pagina": pagina, "tamanhoPagina": 500,
             "ordenarPor": "idItemCompra"},
            limitador, disjuntor,
        )
        registros = payload.get("resultado") or []
        total_declarado = total_declarado or payload.get("totalRegistros")

        if not registros:
            break

        yield pagina, payload
        total_lido += len(registros)
        estado.salvar_checkpoint(run_id, particao, pagina)
        pagina += 1

    # Validação de completude nível 1: o que a API disse que existia
    # precisa bater com o que efetivamente lemos.
    if total_declarado is not None and total_lido != total_declarado:
        raise ErroTransitorio(
            f"Completude: lidos {total_lido} de {total_declarado} declarados "
            f"na partição {particao} — partição marcada como parcial"
        )


# ==========================================================================
# Execução de uma partição
# ==========================================================================


def coletar_particao(cliente, armazenamento: Armazenamento, estado: RepositorioEstado,
                     ano_mes: str, run_id: str) -> dict:
    """Coleta uma partição (classe x ano-mês) e grava o bruto no bronze."""
    limitador, disjuntor = Limitador(REQ_POR_SEGUNDO), DisjuntorCircuito()
    particao = f"classe={CODIGO_CLASSE_MEDICAMENTOS}/ano_mes={ano_mes}"

    wm = estado.watermark(particao)
    desde = (wm - timedelta(days=DIAS_SOBREPOSICAO)) if wm else None

    params = {
        "codigoClasse": CODIGO_CLASSE_MEDICAMENTOS,
        "dataAtualizacaoInicial": desde.date().isoformat() if desde else None,
    }

    manifesto = {
        "run_id": run_id, "particao": particao,
        "inicio": datetime.now(timezone.utc).isoformat(),
        "params": params, "arquivos": [], "n_registros": 0, "status": "em_execucao",
    }

    try:
        max_atualizacao = wm
        for pagina, payload in paginar(cliente, params, estado, run_id, particao,
                                       limitador, disjuntor):
            chave = f"raw/{particao}/run={run_id}/pagina={pagina:05d}.json.gz"
            # Bronze recebe o payload EXATAMENTE como veio: nenhuma conversão,
            # nenhum renome. É o que permite reprocessar sob nova regra.
            import gzip
            bruto = gzip.compress(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
            uri = armazenamento.gravar(chave, bruto)

            registros = payload.get("resultado") or []
            manifesto["arquivos"].append({"uri": uri, "n": len(registros)})
            manifesto["n_registros"] += len(registros)

            for reg in registros:
                dt = reg.get("dataHoraAtualizacaoItem")
                if dt:
                    d = datetime.fromisoformat(dt.replace("Z", "+00:00"))
                    max_atualizacao = max(max_atualizacao or d, d)

        manifesto["status"] = "completo"
        if max_atualizacao:
            # Watermark só avança quando a partição fechou completa.
            estado.salvar_watermark(particao, max_atualizacao)

    except CircuitoAberto as exc:
        manifesto["status"] = "parcial"
        manifesto["erro"] = str(exc)
        log.error("Circuito aberto em %s: %s", particao, exc)
    except ErroDefinitivo as exc:
        manifesto["status"] = "falha_contrato"
        manifesto["erro"] = str(exc)
        log.critical("Provável mudança de contrato da API: %s", exc)
        raise
    finally:
        manifesto["fim"] = datetime.now(timezone.utc).isoformat()
        estado.salvar_manifesto(manifesto)

    return manifesto


# ==========================================================================
# Promoção bronze -> silver (SCD tipo 2, idempotente)
# ==========================================================================

SQL_MERGE_SCD2 = """
-- Idempotente: reexecutar o mesmo dia não cria duplicidade.
-- Só promove partições cujo manifesto esteja 'completo'.
MERGE INTO silver.item_compra_hist AS destino
USING (
    SELECT *
    FROM bronze.item_compra_stage
    WHERE run_id = :run_id
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY idItemCompra
        ORDER BY dataHoraAtualizacaoItem DESC
    ) = 1                          -- dentro da carga, a versão mais recente
) AS origem
ON  destino.idItemCompra = origem.idItemCompra
AND destino.valido_ate IS NULL     -- compara apenas com a versão vigente

-- Retificação na fonte: fecha a versão vigente
WHEN MATCHED AND origem.dataHoraAtualizacaoItem > destino.dataHoraAtualizacaoItem
    THEN UPDATE SET destino.valido_ate = origem.dataHoraAtualizacaoItem,
                    destino.fechado_por_run = :run_id

-- Registro novo (ou nova versão, inserida no ciclo seguinte do MERGE)
WHEN NOT MATCHED
    THEN INSERT (..., valido_de, valido_ate, run_id)
         VALUES (..., origem.dataHoraAtualizacaoItem, NULL, :run_id);

-- Coleta sobreposta com a mesma dataHoraAtualizacaoItem cai em
-- 'MATCHED sem condição satisfeita' e é simplesmente ignorada.
"""


def gerar_particoes(inicio: date, fim: date) -> list[str]:
    """Lista de partições ano-mês, para carga histórica e backfill."""
    out, atual = [], date(inicio.year, inicio.month, 1)
    while atual <= fim:
        out.append(f"{atual:%Y-%m}")
        atual = date(atual.year + (atual.month == 12), (atual.month % 12) + 1, 1)
    return out
