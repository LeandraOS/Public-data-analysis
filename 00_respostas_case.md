# Respostas ao Case Técnico

Este documento responde por escrito às seis etapas pedidas no case. Todos os
números aqui podem ser conferidos rodando o notebook
`notebooks/case_compras_medicamentos.ipynb`; o relatório já executado está em
`outputs/case_compras_medicamentos.html`.

A base tem 2.706 compras de três medicamentos genéricos — AAS, Ácido Fólico e
Aciclovir — feitas por órgãos públicos brasileiros entre dezembro de 2021 e
julho de 2025.

## Resumo antes de entrar nos detalhes

A base parece limpa numa primeira olhada: sem células vazias, sem linhas
duplicadas, todos os CNPJs válidos. O problema aparece quando você olha o
significado dos dados, não só o formato. Encontrei três formas diferentes de
marcar "sem informação" no mesmo arquivo — uma delas é literalmente um
espaço em branco, que numa tabela parece célula vazia mas não é. Alguns
preços estão claramente errados: uma compra registra R$ 253.300 por um único
comprimido de AAS, porque o valor do lote inteiro foi digitado no lugar do
preço unitário. A mesma empresa aparece com até três nomes diferentes.

Sobre os preços em si: o mesmo comprimido, do mesmo fabricante, custa até
duas vezes mais dependendo de quem compra. A maior parte dessa diferença
acontece dentro do mesmo estado, entre municípios vizinhos — não é uma
questão de logística regional. Comprar em grande quantidade ajuda a baixar o
preço, mas menos do que se imagina: multiplicar o volume por dez baixa o
preço uns 14%, não pela metade. Comprar por dispensa de licitação em vez de
pregão custa, em média, 18% mais caro no mesmo item. E não falta concorrência
entre os fornecedores — o mercado é bem distribuído, com quase 300 empresas
diferentes fornecendo cada medicamento.

Juntando essas três últimas coisas: os preços variam bastante, a escala
explica só uma parte pequena dessa variação, e não é falta de concorrência.
Então o problema está em como cada órgão compra, não em quem vende. Isso é
uma notícia melhor do que parece — dá para resolver com informação e
organização (mostrar pro gestor qual é o preço de referência, juntar compras
entre municípios, evitar dispensa em itens de demanda previsível), sem
precisar de fiscalização pesada.

Em reais: somando só o que foi pago acima da mediana de cada grupo, dá
R$ 617 mil; acima do percentil 10, dá R$ 4,2 milhões — sobre R$ 49,4 milhões
homologados nesses três medicamentos.

---

# Etapa 1 — Como coletar esses dados de uma API

O case pede uma arquitetura para coletar de **APIs públicas em geral** — o
Compras.gov é só o exemplo usado no exercício, não o alvo exclusivo. Por
isso, o desenho abaixo não depende de nenhum detalhe específico dessa API:
ele resolve os quatro problemas que o próprio enunciado lista como comuns a
qualquer API pública (disponibilidade, desempenho, documentação, mudanças no
tempo), e funcionaria do mesmo jeito para o PNCP, o Portal da Transparência
ou qualquer outra fonte parecida. No final desta etapa, mostro como esse
desenho se aplica ao Compras.gov especificamente — mas isso é só um exemplo
aplicado, não parte da arquitetura.

## O que a base me ensinou sobre esse tipo de fonte

Antes de desenhar qualquer coisa, vale entender o que a própria base revela
sobre como uma API assim se comporta.

**Ela reescreve o passado.** Boa parte dos itens foi atualizada mais de um
ano depois da compra original — e encontrei casos de itens que mudaram
completamente de fornecedor e de quantidade depois de já registrados. Isso
significa que uma coleta que só busca "o que é novo" não é suficiente: ela
vai perder as correções que a fonte faz depois. É preciso um jeito de
capturar também o que mudou em registros antigos.

**O arquivo que recebi já passou por outras mãos.** Um código de município
aparece formatado como número decimal, tem uma string "nan" (que é como o
Python escreve "não é um número" quando alguém salva isso como texto), e um
campo de marca tem um pedaço de código HTML colado no meio do nome. Tudo isso
indica que, em algum momento entre a API e o arquivo que recebi, o dado
passou por uma planilha ou por algum processo de extração de tela. A
consequência prática: uma coleta direta da API, sem esses intermediários,
evita esse tipo de problema.

**O recorte que peguei é pequeno; a fonte completa não é.** Uma classe de
produto, em quatro anos, já dá quase três mil linhas. O total de compras
públicas no Brasil é ordens de grandeza maior. Isso quer dizer que qualquer
coleta séria precisa pensar em como buscar os dados em partes, sem
sobrecarregar o servidor e sem perder nada no meio do caminho.

## Como eu estruturaria a coleta

**Guardar tudo antes de interpretar qualquer coisa.** A resposta que a API
devolve deve ser salva exatamente como veio, sem nenhuma conversão, num lugar
que não permite alteração depois de escrito. Se mais tarde eu perceber que
interpretei um campo errado, corrijo a interpretação sem precisar buscar tudo
de novo — porque o dado original continua guardado, intacto.

**Duas rotinas em vez de uma.** Uma coleta diária busca só o que mudou desde
a última execução (usando o campo de data de atualização, não a data da
compra — porque, como vimos, o dado muda depois do fato). Uma segunda
rotina, mais espaçada, revarre um período maior e compara o total com o que
já temos guardado, pra pegar qualquer mudança que a primeira rotina não
tenha percebido.

**Nunca sobrescrever, sempre guardar a versão anterior.** Quando um registro
muda, a versão antiga não desaparece — fica marcada como superada, mas
continua acessível. Isso permite responder, se alguém perguntar, "o que essa
compra dizia há seis meses?" — uma pergunta que a base que recebi, sem esse
histórico, não consegue responder.

**Se a estrutura mudar, parar e avisar — nunca continuar calado.** Se um
campo desaparecer ou mudar de tipo de um dia para o outro, prefiro que a
coleta pare e alguém seja avisado, em vez de deixar rodando e gerar números
errados sem ninguém notar.

**Fazer tudo de um jeito que pode ser repetido sem medo.** Rodar a mesma
coleta duas vezes precisa dar exatamente o mesmo resultado. É isso que
permite, se algo falhar no meio do caminho, simplesmente tentar de novo, sem
ter que descobrir manualmente o que já tinha sido salvo e o que não tinha.

## Paginação e limite de requisições

Quando a API oferece paginação por um identificador crescente (buscar
"tudo depois do id X"), prefiro esse método a paginar por número de página,
porque paginar por número de página falha se alguém estiver alterando os
dados enquanto eu ainda estou buscando. Quando só existe paginação por
número de página, compenso buscando em blocos de tempo menores.

Para não sobrecarregar a API, calculo com antecedência quantas requisições
por segundo são razoáveis e limito o próprio programa a isso — em vez de
simplesmente disparar requisições e reagir só quando a API recusar. Isso
importa porque é um serviço público mantido com recurso público; sobrecarregar
sem necessidade tem custo real para quem mantém o sistema.

## O que fazer quando algo dá errado

Erros de rede acontecem. A resposta certa depende do tipo de erro:

- se o erro parece temporário (a API demorou, ou devolveu um erro de
  servidor), tento de novo depois de esperar um pouco, aumentando o tempo de
  espera a cada nova tentativa;
- se a API disser explicitamente "espere e tente de novo", eu respeito esse
  aviso em vez de insistir;
- se o erro for porque eu mandei algo errado (um parâmetro inválido, por
  exemplo), não faz sentido tentar de novo — é um problema no meu código, não
  na rede, e o certo é registrar isso e avisar alguém;
- se a API ficar fora do ar por muito tempo, o sistema para de tentar por um
  período e só volta a checar de vez em quando, em vez de continuar batendo
  na porta sem parar.

E se o processo inteiro cair no meio de uma coleta longa, ele precisa
conseguir retomar de onde parou, sem repetir trabalho já feito e sem perder
nada.

## Como saber se a coleta funcionou

Divido a verificação em três perguntas, nessa ordem:

A coleta rodou até o fim, sem partes faltando? A informação, agora guardada,
é internamente coerente — os tipos batem, os valores fazem sentido? E,
comparando com a coleta anterior, o resultado é parecido com o esperado, ou
teve uma queda ou aumento súbito que merece investigação?

Essa terceira pergunta é a que mais frequentemente passa batido. Uma coleta
pode não ter nenhum erro técnico e ainda assim trazer, por exemplo, a metade
dos registros que trazia no mês anterior — o que quase sempre é sinal de
algo errado que só aparece quando você compara com o histórico.

## Registro do que aconteceu em cada execução

Cada execução da coleta grava um registro estruturado, com um identificador
único, para que seja possível depois responder perguntas como "quantas
tentativas foram feitas essa semana" ou "qual foi o tempo médio de resposta".
Separo os alertas em três níveis: os que exigem ação imediata (por exemplo,
autenticação falhando, ou nenhum dado novo chegando há dois dias), os que
podem esperar até o próximo dia útil, e os que só ficam registrados para
consulta, sem gerar alarme.

## Aplicando isso ao Compras.gov, como exemplo

Usando o índice de endpoints do Swagger do Compras.gov, consegui identificar
qual endpoint provavelmente gerou esta base: o módulo de pesquisa de preços,
no endpoint que retorna o detalhe por item de compra. Um achado interessante
é que existe uma versão desse mesmo endpoint que devolve um arquivo CSV
completo, em vez de página por página — o que sugere usar esse CSV para a
carga inicial (todo o histórico de uma vez) e reservar a busca paginada para
as atualizações do dia a dia. É um bom exemplo de algo que vale checar em
qualquer API antes de decidir a estratégia: se existe uma exportação em lote
além da busca paginada, ela costuma ser mais barata para cargas grandes.

Também descobri, olhando o índice, que existem endpoints de referência para
a unidade de fornecimento e para o cadastro de órgãos e unidades gestoras —
o que confirma que esses são valores de catálogo publicados pela própria
fonte, não texto livre.

O que não consegui confirmar, porque o índice do Swagger não mostra os
parâmetros de cada endpoint em detalhe: se existe filtro por data de
atualização, como funciona a paginação exatamente, e — o ponto mais
importante — se existe algum lugar que documente o significado dos códigos
de modalidade e critério de julgamento. Não encontrei essa documentação em
nenhum dos módulos públicos. Por isso, a leitura que uso mais adiante para
esses dois campos é uma hipótese bem sustentada por evidência da própria
base, não um fato confirmado pela fonte.

---

# Etapa 2 — Entendendo a base e sua qualidade

## Como a base está organizada

Cada linha é um item de uma compra. O identificador de item nunca se repete,
o que confirma isso. Os itens se agrupam em compras (em média, cada compra
tem menos de dois itens), e as compras se agrupam por unidade gestora e por
órgão. Ao todo, são 27 estados, mais de 600 unidades gestoras diferentes e
526 CNPJs de fornecedores, somando R$ 53,4 milhões.

Um ponto importante: a base não é uma amostra geral de medicamentos. São só
três produtos, todos genéricos simples e de baixo custo unitário. Qualquer
conclusão daqui vale para esse tipo de produto — não necessariamente para
remédios de alto custo ou biológicos.

## O que fica evidente e o que só aparece com atenção

Se eu rodasse qualquer verificador automático de qualidade nesta base, ele
passaria sem apontar nada de errado: zero células vazias, zero linhas
duplicadas, todos os CNPJs com dígito verificador correto. O problema é que
"bem formado" e "correto" são coisas diferentes, e os problemas reais só
aparecem quando você pergunta o que cada dado quer dizer, não só se ele tem o
formato certo.

**Ausência disfarçada.** A base marca "sem informação" de três formas
diferentes: o texto "NA", um único espaço em branco (que parece célula vazia
mas tecnicamente não é), e a palavra "nan" (que aparece quando alguém salva
um valor ausente do Python como se fosse texto comum). Encontrei o problema
do espaço em branco por acidente, porque um teste automático que eu tinha
escrito começou a falhar sem motivo aparente — investigando, descobri que
aquelas células "vazias" na verdade continham um espaço, invisível numa
tabela normal.

**Preços impossíveis.** Alguns preços não fazem sentido — o extremo é
R$ 253.300 por um único comprimido de AAS, quando o normal fica em torno de
cinco centavos. Olhando mais de perto, percebi um padrão: nesses casos, a
quantidade registrada é sempre 1, o que sugere que alguém digitou o valor
total do lote inteiro no campo que deveria ter o preço de um único
comprimido.

**A mesma empresa com nomes diferentes.** Encontrei 48 CNPJs que aparecem
com mais de uma razão social — em alguns casos por mudança real no tipo de
empresa, em outros por diferenças de grafia ou truncamento do texto. Se eu
tivesse contado fornecedores pelo nome em vez do CNPJ, teria inflado o número
de concorrentes e escondido a concentração real do mercado.

**Um campo de marca que muitas vezes não tem marca.** Em mais de uma a cada
dez linhas, o campo que deveria trazer o laboratório do medicamento traz
outra coisa: a palavra "genérico", o nome da unidade de fornecimento, texto
de edital, e em um caso um pedaço de código de programação colado no meio.
Por isso não uso esse campo para nenhuma análise por marca.

**Preço em embalagens diferentes.** O mesmo medicamento aparece com preço por
comprimido, por cápsula, por bisnaga, por frasco — e comparar esses preços
diretamente seria como comparar o preço de uma caixa com o de uma unidade.
Restrinjo as comparações de preço aos casos em que a embalagem é a mesma.

**Registros que mudaram depois de criados.** Encontrei três casos em que o
mesmo item de compra aparece duas vezes, com fornecedor e quantidade
diferentes — não é erro de duplicação, é retificação: o sistema de origem
corrigiu a informação depois. Isso já foi discutido na Etapa 1 e é o motivo
pelo qual a coleta precisa lidar com atualizações, não só com novidades.

**Dois campos sem explicação no dicionário.** O código de modalidade e o
critério de julgamento aparecem na base sem descrição do que significam.
Encontrei um padrão bem forte na relação entre esses dois campos e um
terceiro (o percentual de desconto), que me deixa bastante confiante de que
um dos códigos significa "pregão" e o outro "dispensa de licitação", e que
as letras do critério significam "menor preço" e "maior desconto". Mas,
como expliquei na Etapa 1, não encontrei nenhuma fonte oficial que confirme
isso — então trato como hipótese em todo lugar onde uso essa leitura.

## O que decidi fazer com cada problema

A regra que segui em todos os casos: nenhuma linha é apagada. Cada problema
vira uma marcação na própria base, e qualquer exclusão só acontece no momento
de calcular alguma coisa específica — nunca de forma permanente. Isso
significa que, se alguém quiser revisar uma decisão minha, consegue fazer
isso sem precisar processar tudo de novo desde o início.

Especificamente: os três formatos de ausência viram um único valor nulo de
verdade, tratado sempre da mesma forma. Os preços implausíveis ficam
marcados e saem só das contas de preço, continuando disponíveis para outras
análises. A identidade de cada fornecedor passa a ser o CNPJ, não o nome —
e para medir concorrência, uso os oito primeiros dígitos do CNPJ, que
identificam o grupo econômico, não a filial isolada. Quando um item aparece
em duas versões, mantenho a mais recente como principal e guardo a antiga
como histórico, em vez de simplesmente descartá-la.

---

# Etapa 3 — Preparando os dados para análise

O código que faz esse tratamento está dividido em partes pequenas, cada uma
com uma responsabilidade única: uma parte só lê o arquivo, sem interpretar
nada; outra só verifica problemas, sem corrigir nada; outra só corrige,
usando o que a verificação encontrou. Essa separação existe porque misturar
"ler", "verificar" e "corrigir" numa função só torna muito difícil, mais
tarde, entender por que um número específico ficou do jeito que ficou.

Na leitura, tudo entra como texto, sem nenhuma conversão automática de tipo.
Prefiro fazer essa conversão manualmente, na etapa seguinte, porque deixar o
programa decidir sozinho o que é número e o que é texto ausente é
exatamente o tipo de decisão silenciosa que causou o problema do espaço em
branco.

Depois da leitura, alguns identificadores (CNPJ, código de município) ficam
como texto, porque convertê-los para número apagaria zeros à esquerda e os
tornaria inúteis. Três colunas foram descartadas porque não tinham nenhuma
informação (uma delas estava sempre vazia, e as outras duas tinham sempre o
mesmo valor em toda a base). Criei também algumas colunas novas: o valor
total de cada item (quantidade vezes preço), o logaritmo do preço e da
quantidade (que facilita a análise estatística mais adiante), e uma marcação
indicando se cada item entra ou não na comparação de preços.

Duas decisões que tomei por não fazer, e que acho importante deixar
explícitas: não completei nenhum valor ausente com estimativa — onde falta
informação, o relatório simplesmente diz "não informado", porque inventar um
número, mesmo com boa intenção, corre o risco de parecer um dado real. E não
corrigi os preços pela inflação, porque não tinha uma base sólida para
escolher um índice específico para esses três produtos; prefiro declarar
essa limitação do que aplicar uma correção sem fundamento.

---

# Etapa 4 — O que os dados mostram

Fiz três perguntas, escolhidas porque uma leva à outra: a primeira mede o
problema, a segunda testa a explicação mais óbvia para ele, e a terceira
investiga o que ainda sobra depois de descontar essa explicação. Todas as
contas de preço usam só os itens que passam pelo filtro de comparabilidade —
cerca de 90% da base.

## Pergunta 1 — O preço do mesmo remédio varia muito entre compradores?

Essa é a pergunta mais direta que dá pra fazer sobre eficiência de compra
pública: se o mesmo produto, com o mesmo código de catálogo, custa preços
muito diferentes, isso é dinheiro público sendo gasto de forma desigual sem
nenhuma razão óbvia.

Comparando só itens idênticos (mesmo código, mesma embalagem) e sem os
preços claramente errados, o comprador que paga mais caro (considerando os
10% mais caros) paga entre 1,8 e 2,3 vezes o que paga o comprador mais
barato (os 10% mais baratos), dependendo do medicamento.

O dado mais importante aqui não é esse número — é de onde vem essa
diferença. Calculando quanto dessa variação acontece entre estados
diferentes e quanto acontece dentro do mesmo estado, a resposta é clara:
cerca de 86% da diferença está dentro do mesmo estado, entre municípios
vizinhos. Isso muda completamente a explicação possível. Se a diferença
fosse principalmente entre estados, poderíamos culpar frete ou diferenças
regionais de mercado. Como ela é majoritariamente dentro do mesmo estado,
entre compradores que enfrentam basicamente o mesmo mercado fornecedor, a
explicação mais provável é diferença na capacidade de negociar e comparar
preços — algo que se resolve com informação, não com infraestrutura.

Vale notar: isso é depois de já ter limpo os erros óbvios. A diferença
absoluta em reais parece pequena (poucos centavos por comprimido), mas
multiplicada pelo volume total comprado no país, chega a valores relevantes.

**Limitações:** os valores usados são nominais, sem correção pela inflação
ao longo dos quatro anos; e a comparação usa como referência a própria
mediana da base, então, se todo o mercado estivesse pagando acima do preço
justo, essa análise não teria como perceber isso — precisaria de um preço de
referência externo, como o teto regulado pela Anvisa.

## Pergunta 2 — Comprar em grande quantidade sai mais barato?

Essa pergunta importa porque sustenta uma política concreta: juntar compras
de vários municípios em um consórcio, ou centralizar a compra num nível mais
alto de governo. Se o volume não fizer diferença no preço, fragmentar a
compra entre milhares de municípios não tem custo real. Se fizer diferença
grande, centralizar passa a ter justificativa numérica, não só intuição.

Relacionei o preço com a quantidade comprada, usando uma técnica estatística
que trata as duas variáveis em escala logarítmica — o que permite ler
diretamente "quanto o preço cai, em porcentagem, quando o volume dobra".
Controlei também pelo medicamento e pelo ano da compra, porque os três
produtos têm preços de base bem diferentes e ignorar isso distorceria o
resultado.

O resultado: multiplicar a quantidade comprada por dez reduz o preço unitário
em cerca de 14%. Isso é um efeito real e consistente entre os três
medicamentos, mas é mais modesto do que a intuição sugere — não é "comprar
junto corta o preço pela metade". Um dado que reforça essa leitura: os
consórcios intermunicipais de saúde, que de fato compram em grande volume,
pagam cerca de 20% abaixo da mediana — um pouco melhor do que a escala por si
só explicaria, o que sugere que consórcios trazem algum ganho extra, além do
volume puro (talvez capacidade técnica de negociação).

**Limitações:** essa é uma relação estatística, não uma prova de causa e
efeito. Compradores que compram muito diferem de compradores pequenos em
várias outras coisas além do volume — capacidade técnica, poder de
negociação, previsibilidade da demanda — e parte do desconto observado pode
vir dessas outras diferenças, não só do volume em si.

## Pergunta 3 — A forma de contratar e a concorrência entre fornecedores importam?

Descontado o efeito do volume, restam duas explicações institucionais
possíveis para a diferença de preços. A primeira: a lei permite comprar sem
licitação completa (por "dispensa") em certas situações, e essa forma mais
rápida pode custar mais caro. A segunda: se poucos fornecedores dominarem o
mercado, isso por si só explicaria preços mais altos.

Comparei o preço de compras feitas por dispensa contra compras feitas por
pregão comum, controlando pelo medicamento, ano e volume. A diferença é de
cerca de 18% mais caro nas compras por dispensa — e, olhando só o AAS, sem
nenhum controle estatístico, a diferença bruta chega a 70%.

Sobre concorrência: calculei o quanto cada mercado está concentrado nas mãos
de poucos fornecedores, usando o CNPJ agrupado por grupo econômico. Em
nenhum dos três medicamentos o mercado está concentrado — pelo contrário, há
entre 268 e 288 grupos econômicos diferentes fornecendo cada um, e os índices
de concentração ficam todos na faixa considerada de baixa concentração.

Juntando isso com as duas perguntas anteriores: os preços variam bastante
(pergunta 1), a escala explica só uma parte pequena dessa variação (pergunta
2), e não é falta de concorrência entre fornecedores (pergunta 3). Por
eliminação, o problema está em como cada comprador negocia e planeja a
compra — não em quem vende. E dispensar a licitação, especificamente, parece
custar mais caro em vez de mais barato, o que sugere que vale reservar essa
modalidade para situações realmente excepcionais, não para itens de compra
rotineira como esses três medicamentos.

**Limitações:** a leitura de qual código significa "dispensa" e qual
significa "pregão" é a hipótese discutida na Etapa 2 — se estiver errada, os
números de preço continuam válidos, mas a interpretação institucional muda.
E o índice de concentração mede quem venceu a licitação, não quantos
participaram dela — um mercado pode ter poucos vencedores recorrentes mesmo
com muitos concorrentes tentando.

## E ao longo do tempo?

Olhando a evolução ano a ano, o preço nominal subiu em 2022, ficou estável
em 2023 e 2024, e caiu em 2025. Sem corrigir pela inflação (que no período
somou uns 15% a 18%), essa estabilidade nominal na verdade esconde uma queda
real de preço bem relevante. Vale lembrar que os dados de 2025 ainda são
parciais e sujeitos a correção — como vimos na Etapa 2, essa fonte atualiza
registros bem depois da data da compra.

## Quanto isso representa em dinheiro

Para dar uma ideia concreta, calculei quanto foi pago acima de três
referências diferentes: a mediana, o percentil 25 e o percentil 10 de cada
grupo (mesmo produto, mesmo ano). Acima da mediana, a soma é R$ 617 mil;
acima do percentil 10, R$ 4,2 milhões — sobre um total de R$ 49,4 milhões
homologados nesse recorte.

Uso três referências e não uma, de propósito: um número único sugeriria uma
meta, e nem todo comprador pode realisticamente chegar no percentil 10. O que
esses números mostram com segurança é a ordem de grandeza — alguns milhões
de reais, em só três medicamentos genéricos, dentro de um recorte bem
pequeno da compra pública total.

---

# Etapa 5 — Indicadores para acompanhar isso de forma contínua

Proponho quatro indicadores. Os dois primeiros formam um par que precisa ser
lido junto — explico o motivo ao final desta seção.

## Indicador 1 — Índice de Preço Relativo

Mede se um comprador paga mais ou menos que o preço típico do país, para o
mesmo remédio, no mesmo período. O cálculo divide o preço pago pela mediana
nacional daquele item naquele trimestre. Um valor de 1,2 significa "20% mais
caro que a mediana nacional".

Uso mediana em vez de média porque um único preço muito errado bastaria para
distorcer uma média — como vimos, isso realmente acontece na base. Calculo
por trimestre porque, mês a mês, alguns grupos ficam pequenos demais para uma
mediana confiável.

**Limitação principal:** esse indicador não leva em conta o volume comprado,
então ele naturalmente aponta como "caros" os compradores que compram pouco
— não necessariamente os que negociam mal. É por isso que existe o segundo
indicador.

## Indicador 2 — Índice de Preço Ajustado por Escala

Faz a mesma comparação do indicador 1, mas descontando primeiro o efeito
esperado do volume (usando a relação que estimei na pergunta 2 da Etapa 4).
Depois disso, calcula não só a razão de preço, mas o excesso pago em reais —
o que é mais útil para decidir onde vale a pena investigar primeiro.

Ordenar pelo indicador 1 puro coloca no topo hospitais militares que compram
poucas unidades — eles pagam mais caro, mas simplesmente porque compram
pouco, não porque negociam mal. Ordenar pelo excesso em reais do indicador 2
muda completamente a lista, e passa a apontar onde há dinheiro relevante em
jogo. Esse contraste, por si só, é uma lição: vale sempre checar quem um
indicador coloca no topo antes de publicá-lo, porque a fórmula pode estar
certa e o resultado ainda assim induzir a uma conclusão errada.

**Limitação:** depende de uma estimativa (o efeito da escala), que tem
incerteza e pode mudar com o tempo — por isso proponho reestimá-la uma vez
por ano.

## Indicador 3 — Taxa de Uso de Dispensa

Mede que fração das compras de um órgão foi feita por dispensa de licitação,
em vez de pregão — tanto em número de itens quanto em valor. Como vimos que
dispensa custa em média 18% mais caro, acompanhar essa taxa ajuda a
identificar onde vale investigar se a exceção está sendo usada mais do que o
necessário.

**Limitações:** depende da hipótese sobre o significado dos códigos, discutida
nas etapas anteriores; e dispensa é legal e às vezes necessária — uma taxa
alta é um sinal para investigar, não uma conclusão de irregularidade.

## Indicador 4 — Concentração de Fornecedores

Mede, para cada medicamento, o quanto o mercado está concentrado nas mãos de
poucos grupos econômicos — o mesmo cálculo que usei na pergunta 3. Serve como
alerta de risco: se a concentração começar a subir com o tempo, isso é sinal
de dependência crescente de poucos fornecedores.

**Limitação:** mede concentração entre quem venceu a licitação, não entre
quem participou dela.

## Que outra base ajudaria

Cruzar com o Portal da Transparência ou o SIAFI resolveria a limitação mais
importante: hoje o valor que uso é o valor homologado na licitação, não
necessariamente o valor efetivamente pago depois. Cruzar com a tabela de
preços máximos da Anvisa resolveria outra limitação, permitindo comparar o
preço pago com um teto regulado, em vez de só com a mediana da própria base.
E cruzar com o cadastro de empresas da Receita Federal permitiria checar se
algum fornecedor estava irregular ou inativo na data da compra.

---

# Etapa 6 — Como isso pode ser reproduzido

O código está dividido em módulos pequenos, cada um com uma única
responsabilidade, na ordem em que são usados: primeiro lê o arquivo sem
interpretar nada, depois verifica problemas de qualidade sem corrigir nada,
depois corrige o que foi encontrado, depois faz as análises, depois calcula
os indicadores. Essa ordem é sempre a mesma — nenhuma etapa depende de algo
que só existe numa etapa posterior.

O próprio notebook não repete o código: ele importa as mesmas funções que
estão nos módulos, então o número que aparece no relatório é sempre calculado
pela mesma função que rodaria de novo, e não por uma cópia solta dentro do
notebook.

Para rodar tudo:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest -q
jupyter nbconvert --to html --execute notebooks/case_compras_medicamentos.ipynb --output-dir outputs
```

Todos os limites e parâmetros usados (o que conta como preço implausível, o
tamanho mínimo de grupo para calcular uma mediana confiável, e assim por
diante) estão reunidos num único arquivo de configuração, em vez de
espalhados pelo código — então revisar ou ajustar uma dessas escolhas não
exige caçar onde ela está escondida.

Escrevi 37 testes automáticos, e dois deles encontraram problemas reais
durante o desenvolvimento: foi um teste que falhou, sem eu saber o motivo de
imediato, que me levou a descobrir o problema do espaço em branco disfarçado
de célula vazia. Nenhuma inspeção visual da tabela teria mostrado isso. É o
melhor argumento que tenho para dizer que testar dados automaticamente vale a
pena, mesmo numa base que parece pequena e simples.

---

# O que ficou de fora, resumido

O valor usado é o valor homologado, não necessariamente o pago depois. A
análise cobre só três medicamentos genéricos de baixo custo — nada aqui se
aplica automaticamente a remédios de alto custo ou biológicos. As relações
encontradas (efeito da escala, efeito da dispensa) são estatísticas, não
provas de causa e efeito. A referência de preço usada vem da própria base,
então não detectaria um sobrepreço generalizado no mercado inteiro. Os
valores não foram corrigidos pela inflação. Não sei se esta base é o
universo completo de compras dessa classe de produto ou uma amostra, o que
limita qualquer afirmação sobre totais nacionais. Os dados mais recentes
(2025) ainda estão sujeitos a atualização pela fonte. E a leitura dos códigos
de modalidade e critério de julgamento é uma hipótese bem sustentada, mas não
confirmada por documentação oficial.
