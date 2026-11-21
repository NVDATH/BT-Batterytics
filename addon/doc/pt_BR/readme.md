# BT-Batterytics

O BT-Batterytics informa a bateria de dispositivos Bluetooth, registra por quanto tempo cada um fica conectado entre duas recargas e mostra estatísticas.

É uma versão modificada do [BlueToothBatteryReport](https://github.com/haitun001/BlueToothBatteryReport), de haitun001 e cary-rowen (veja Créditos e licença).

Suporta vários dispositivos e anuncia em sequência todos os dispositivos Bluetooth cuja bateria pode ser detectada. Ordem: conectados, desconhecidos, desconectados.

## Atalho

- `NVDA+Shift+B` em computadores sem bateria (desktops), `NVDA+Alt+B` em computadores com bateria (notebooks ou tablets) — Pressione uma vez para ouvir o status, duas para copiar o relatório à área de transferência e três para abrir as configurações.

NVDA+Shift+B é o comando de bateria do próprio NVDA. Como desktops não têm bateria, o complemento usa esse gesto neles. Em computadores com bateria, usa NVDA+Alt+B para preservar o comando do NVDA. A escolha é feita ao iniciar o NVDA, com base no Windows; se ele não puder determinar, presume-se que há bateria. Altere o gesto em NVDA → Preferências → Gestos de entrada, categoria BT-Batterytics. Ela também contém “Abrir as estatísticas da bateria Bluetooth”, sem gesto padrão.

## Formato falado

Quando há informação de bateria, cada dispositivo é anunciado assim:

- `nome do dispositivo bateria xx%`

Opcionalmente, podem ser mostrados o tipo e o tempo de conexão:

- `nome do dispositivo (Classic) bateria xx%`
- `nome do dispositivo (LE) bateria xx%`
- `nome do dispositivo bateria xx% (conectado 2 h 5 min)`

Se você atribuiu um nome próprio ao dispositivo (veja Estatísticas da bateria), ele é anunciado no lugar do nome dado pelo Windows.

## Configurações

Há uma página dedicada em NVDA → Preferências → Configurações → BT-Batterytics.

### Quais dispositivos informar

- **Informar dispositivos conectados** — Anuncia os atualmente conectados (ativado por padrão).
- **Informar dispositivos desconectados** — Anuncia os emparelhados, mas desconectados.
- **Informar dispositivos com status desconhecido** — Anuncia aqueles cujo status não pode ser determinado. Dispositivos Bluetooth LE geralmente aparecem assim.

### O que anunciar para cada dispositivo

- **Mostrar tipo de conexão (Classic / LE)** — Acrescenta uma indicação de Bluetooth Classic ou Bluetooth Low Energy.
- **Mostrar duração da conexão** — Anuncia há quanto tempo o dispositivo está conectado.
- **Falar o tempo total conectado desde a última recarga** — Escolhe qual tempo anunciar e ativa a medição (ativado por padrão).
  - Marcado: tempo total conectado desde a última recarga. Preservado entre desconexões e reinícios do NVDA; funciona com Classic e LE.
  - Desmarcado: somente o tempo da conexão atual informado pelo Windows. O Windows fornece esse valor apenas para Classic; LE não tem tempo neste modo.
- **Mostrar a estimativa do estojo de recarga no relatório** — Acrescenta as recargas restantes estimadas do estojo à linha dos fones (desativado por padrão, veja Estojo de recarga).

### Estatísticas

- **Ver estatísticas da bateria...** — Abre a janela de estatísticas (abaixo).
- **Número máximo de ciclos concluídos a manter por dispositivo** — De 5 a 5000, padrão 500. Ciclos mais antigos são excluídos acima desse número.
- **Excluir ciclos concluídos mais antigos que este número de dias** — 0 mantém todos (padrão).

### Alertas

- **Ativar alerta de bateria fraca (padrão para todos os dispositivos)** — Alerta quando a bateria de um dispositivo conectado cai abaixo de seu nível de alerta. Cada dispositivo segue esta opção, salvo configuração individual (veja Alertas). O diálogo de bateria fraca é sempre mostrado.
- **Limite padrão de bateria fraca** — Porcentagem que dispara o alerta nos dispositivos sem nível próprio (5–50%, padrão 20%).
- **Métodos de alerta (para todos os alertas)** — Caixas de seleção combináveis:
  - **Falar o alerta** (marcado por padrão)
  - **Reproduzir dois bipes**
  - **Reproduzir o som do alerta** (veja Sons dos alertas)
- **Abrir pasta de sons...** — Abre a pasta dos arquivos para substituí-los.
- **Alertas de queda de nível: alertar a cada queda deste número de pontos da bateria** — De 1 a 50, padrão 10.
- **Verificar mudanças na conexão dos dispositivos a cada número de segundos** — De 5 a 300, padrão 15. Usado apenas enquanto algum dispositivo tiver alerta de conexão ou desconexão.

## Acompanhamento do tempo conectado

O complemento registra o tempo conectado entre duas recargas, permitindo ver a autonomia real por carga. Funciona em segundo plano e é controlado por **Falar o tempo total conectado desde a última recarga**.

- O acompanhamento começa na primeira detecção do dispositivo, em qualquer nível. Por isso, o primeiro ciclo pode ser menor que o real se a bateria não estava cheia.
- Conta apenas o tempo em que o dispositivo é visto como conectado. O tempo desconectado não conta, mas o total anterior é preservado.
- Uma recarga é detectada quando a bateria está pelo menos 15 pontos percentuais acima do menor nível do ciclo atual. Funciona também para dispositivos que nunca chegam a 100%. O ciclo concluído é salvo e a contagem reinicia do zero. Não conta enquanto o nível sobe (carregamento).
- Se o Windows informar que um dispositivo Classic está conectado há mais tempo do que o contado, usa-se o maior valor. LE não tem esse valor, então seu total cobre apenas o período observado pelo complemento.
- Lacunas de mais de 15 minutos entre observações (como durante a suspensão) não contam.
- Ciclos menores que 30 minutos não são salvos como concluídos.
- Dispositivos são identificados pelo endereço Bluetooth, não pelo nome. Dois nomes iguais têm registros separados; renomear no Windows preserva os dados.
- A medição pode ser interrompida (veja Estatísticas da bateria). Os dados ficam preservados, e o tempo conectado passa a ser o informado pelo Windows, se houver.

### Dispositivos que nem sempre ficam conectados

Alguns ficam ligados, mas raramente conectados ao computador. Por exemplo, um teclado de três modos usado com receptor de 2,4 GHz, conectado por Bluetooth apenas para verificar a bateria. Seu tempo conectado é muito curto; ciclos com menos de 30 minutos não são salvos, e não há registros úteis. Para eles, escolha **Contar tempo decorrido** no menu Medição do dispositivo na janela de estatísticas. Desativado por padrão, definido por dispositivo.

Com essa opção:

- O ciclo vai da recarga ao último momento em que o nível foi visto caindo. Não vai até a próxima verificação, pois o nível só é conhecido ao ser lido, e o Windows pode mostrar um valor antigo para um dispositivo desconectado.
- A recarga é detectada na primeira leitura posterior. Seu momento é estimado no meio entre a última leitura anterior e essa leitura.
- As estimativas (carga completa, taxa de consumo, tempo restante, tendência) e a coluna Intervalo entre recargas usam esses tempos, mostrados em dias a partir de dois dias. O primeiro ciclo começa na primeira detecção, qualquer que seja o nível.
- No relatório, a linha mostra o tempo desde a última recarga em vez do tempo conectado.
- Cada ciclo lembra como o tempo foi contado. As estatísticas usam apenas ciclos contados do modo atual do dispositivo. Os demais permanecem na lista, com o método em Tempo contabilizado.
- Mudar o método reinicia o ciclo atual.

Leia a bateria de tempos em tempos: conecte por Bluetooth e pressione o atalho. Quanto menos frequente a leitura, menor a precisão; se houver duas recargas entre leituras, os dois ciclos serão contados como um.

### Dispositivos que não chegam a 0%

Alguns informam um nível que não diminui uniformemente. Por exemplo, um teclado fica em 100% por muito tempo, depois cai rápido e para em 55% ou 60%. Você aprende a recarregá-lo antes, por exemplo a 70%, por segurança. As estimativas (Carga completa, Tempo restante) pressupõem queda uniforme até 0% e ficam excessivamente longas: a duração real entre suas recargas é muito menor.

Escolha **Nível habitual de recarga...** no menu Medição do dispositivo e informe o nível em que recarrega, por exemplo 70. Desativado (0) por padrão, definido por dispositivo.

Com essa opção:

- Carga completa (est.) passa a ser o tempo da bateria cheia até seu nível, ou seja, o intervalo entre suas recargas.
- Tempo restante (est.) passa a ser o tempo até atingir seu nível. É zero se a bateria já estiver nele ou abaixo.
- Taxa de consumo, duração dos ciclos e detecção de recargas não mudam.
- A coluna Medição no resumo mostra o nível, como “ativada, recarregar a 70%”.

Mantenha desativado para dispositivos com queda uniforme. As estimativas continuam aproximadas devido à queda irregular; os números mais confiáveis são os tempos reais entre recargas: Média, Mais curto, Mais longo e Intervalo entre recargas.

## Estatísticas da bateria

**Ver estatísticas da bateria...** nas configurações abre uma janela com duas listas. O comando “Abrir as estatísticas da bateria Bluetooth” em Gestos de entrada abre-a diretamente. Os registros são mostrados mesmo com a medição desativada.

A ordem é a do relatório falado: conectados, desconhecidos, desconectados e, depois, por nome. Dispositivos ausentes na última busca ficam por último.

### Resumo por dispositivo

Uma linha por dispositivo:

- **Status** — Estado de conexão na última busca.
- **Medição** — Desativada, ativada ou ativada com tempo decorrido. O nível habitual de recarga é acrescentado quando definido, como “recarregar a 70%”.
- **Alertas** — Os ativos, como “bateria fraca 20%, queda de nível” ou “nenhum”.
- **Ciclos** — Número de ciclos concluídos.
- **Média**, **Mais curto**, **Mais longo** — Tempo conectado dos ciclos concluídos.
- **Carga completa (est.)** — Autonomia estimada com carga completa, calculada pela bateria usada em cada ciclo. Permite comparar ciclos que não começaram em 100%.
- **Taxa de consumo** — Pontos de bateria por hora conectada ou por dia, quando o consumo é lento.
- **Intervalo entre recargas** — Tempo médio entre duas recargas.
- **Última recarga** — Quando foi detectada a última recarga.
- **Tendência** — Últimos 3 ciclos comparados aos anteriores, como “12% menor” ou “estável” (diferença inferior a 5%). Requer pelo menos 4 ciclos.
- **Tempo restante (est.)** — Tempo conectado restante na taxa habitual de consumo, a partir do último nível observado.
- **Estojo usado (recargas, est.)** e **Estojo restante (recargas, est.)** — Recargas usadas e restantes, apenas para dispositivos com estojo (veja Estojo de recarga). Colunas adicionadas na primeira ativação do estojo; podem ser ocultadas.

### Ciclos

Inicialmente, só aparece o ciclo em andamento (“atual”) de cada dispositivo. Os concluídos ficam recolhidos, mais recentes primeiro. Pressione Space em qualquer linha do dispositivo, clique duas vezes ou use o menu de contexto (tecla Applications) para expandir; repita para recolher. O NVDA diz “Expandido” ou “Recolhido”. Colunas:

- **Ciclo** — Número do ciclo.
- **Estado** — “recolhido” ou “expandido” na linha do ciclo atual; vazio em dispositivos sem ciclos concluídos.
- **Duração** — Tempo conectado do ciclo.
- **Bateria** — Nível inicial e menor nível atingido, como “100% a 23%”.
- **Taxa de consumo** — Pontos de bateria usados por hora nesse ciclo.
- **Carga completa (est.)** — Autonomia estimada com carga completa nesse ciclo.
- **Término** — Quando foi detectada a recarga que encerrou o ciclo.
- **Tempo contabilizado** — Tempo conectado ou decorrido (veja Dispositivos que nem sempre ficam conectados). Adicionada ao usar tempo decorrido pela primeira vez; pode ser ocultada.

As estimativas ignoram ciclos que usaram menos de 10 pontos, pois a bateria Bluetooth costuma ser informada em passos grandes. Célula vazia significa dados insuficientes. Mais ciclos tornam as estimativas mais confiáveis.

## Comandos da janela de estatísticas

As duas listas compartilham comandos. A maioria tem tecla; todos estão no menu de contexto (Applications). Os que abrem submenus ou diálogos vêm primeiro; os que têm tecla ficam por último.

### Medição

Submenu com dois itens marcáveis para o dispositivo:

- **Medir este dispositivo** — Interrompe ou reinicia a medição, preservando dados.
- **Contar tempo decorrido (para dispositivos que nem sempre ficam conectados)** — Conta desde a última recarga em vez do tempo conectado. Veja a seção correspondente.
- **Nível habitual de recarga...** — Nível em que você costuma recarregar dispositivos com informação irregular. Veja Dispositivos que não chegam a 0%.

### Alertas

Alertas do dispositivo. Veja Alertas abaixo.

### Selecionar

Alternar seleção da linha atual (**Control+Space**), Selecionar todas (**Control+A**), Não selecionar nenhuma, Inverter seleção, Selecionar linhas deste dispositivo. As listas permitem seleção múltipla, e o NVDA diz “selecionada” nas linhas escolhidas. Mover só com setas seleciona apenas a linha atual. Para compor uma seleção, use Control+setas e Control+Space em cada linha.

### Ordenar

Sem tecla. Escolha a ordem dos dispositivos (relatório, nome, número de ciclos, tempo médio, estimativa de carga completa, última recarga, tempo do ciclo atual, consumo ou manual) e dos ciclos concluídos de cada dispositivo (mais recentes, antigos, longos, curtos primeiro ou manual). A opção marcada está em uso, e a escolha é lembrada. Com **Manual**, você decide a ordem (veja Mover dispositivo ou ciclo).

### Mover dispositivo ou ciclo

**Control+Shift+Seta para cima** e **Control+Shift+Seta para baixo**. Exige ordenação manual: em Ordenar, escolha Manual em Dispositivos por para mover dispositivos e em Ciclos por para mover ciclos. Ao escolher Manual pela primeira vez para dispositivos, a ordem atual vira sua ordem.

- No resumo e na linha do ciclo atual, as teclas movem o dispositivo com todas as suas linhas.
- Em um ciclo concluído de dispositivo expandido, movem esse ciclo entre os concluídos daquele dispositivo.

O NVDA anuncia a posição, como “2 de 5”; um bipe indica que a linha já está no limite. A ordem é lembrada. Dispositivo detectado pela primeira vez e ciclo recém-concluído ficam primeiro.

### Mover as listas

**Control+Shift+Seta para a esquerda** e **Control+Shift+Seta para a direita** movem a lista com foco antes ou depois da outra. A janela abre na primeira lista, permitindo priorizar a mais consultada. A ordem é lembrada.

### Escolher colunas

Sem tecla. Abre caixas de seleção para cada coluna opcional de cada lista. Dispositivo e Ciclo sempre aparecem. Use Control+Shift+Seta para cima ou para baixo para mover uma coluna; a ordem vale para exibição, cópia e exportação. A escolha é lembrada.

### Expandir e recolher

**Space** na lista de ciclos mostra ou oculta os ciclos concluídos do dispositivo.

### Renomear dispositivo

**F2** atribui um nome ao dispositivo da linha atual. Um nome vazio ou o original restaura o nome do Windows. É usado nas estatísticas, relatório falado e alertas.

### Copiar

- **Control+C** copia a linha atual.
- **Control+Shift+C** copia tudo sobre o dispositivo atual (resumo e todos os ciclos, inclusive recolhidos).

Apenas as colunas visíveis são copiadas, em pares “Cabeçalho: valor”.

### Marcar estojo como carregado

**Control+Shift+R**, apenas em dispositivo com estojo. Informa que você carregou o estojo para reiniciar do zero as recargas usadas. Veja Estojo de recarga.

### Exportar

**Control+E** abre o menu com:

- **O que exportar** — Linhas selecionadas, dispositivo atual ou todas as linhas. A opção marcada está em uso.
- **Incluir valores detalhados** — Marcado por padrão e lembrado. Acrescenta identificação (endereço e ambos os nomes) e valores exatos: segundos, porcentagens, pontos usados, datas ISO 8601. Sem isso, exporta as colunas visíveis.
- **Copiar para a área de transferência como** e **Salvar em arquivo como** — Texto simples, tabela Markdown, CSV, valores separados por tabulação (para colar em planilhas), JSON (números permanecem números) ou tabela HTML. CSV é salvo com marca de ordem de bytes para o Excel mostrar todos os caracteres corretamente.
- **Abrir como relatório HTML no navegador** — Cria uma página com título e tabela e abre no navegador.

As exportações podem ser entregues diretamente a uma pessoa ou ferramenta de IA.

### Atualizar

**F5** busca novamente e atualiza a janela; caso contrário, ela retrata apenas o momento em que foi aberta.

### Excluir

- **Control+Delete** exclui a linha atual, ou todas as selecionadas em uma seleção múltipla.
- **Control+Shift+Delete** exclui o dispositivo da linha atual com todos os dados.

Sempre há uma confirmação (Sim ou Não). No ciclo em andamento, “excluir” reinicia o ciclo do zero. No resumo, excluir uma linha exclui o dispositivo. Se a medição estiver ativa, ele recomeça do zero na próxima verificação.

## Alertas

Cada dispositivo pode ter os alertas abaixo. São escolhidos individualmente na janela de estatísticas (menu de contexto, **Alertas**; a coluna Alertas do resumo mostra os ativos). Todos usam os métodos marcados nas configurações.

### Bateria fraca

Alerta uma vez quando a bateria de um dispositivo conectado fica fraca, sem repetir até a recuperação. Também mostra um diálogo de aviso. **Nível de bateria fraca...**, no menu Alertas, oferece:

- **Usar o padrão** — Segue **Ativar alerta de bateria fraca** e o limite padrão das configurações. Se estiver desativado nelas, não alerta.
- **Usar um nível personalizado** — De 5 a 50%. Alerta nesse nível mesmo com o alerta geral desativado.
- **Nunca alertar para este dispositivo** — Sem alerta de bateria fraca, independentemente das configurações.

### Quedas do nível da bateria

Desativado por padrão. Alerta a cada queda do número de pontos configurado desde o último alerta, a partir do nível da primeira detecção e novamente sempre que subir (carregamento). O passo informado depende do dispositivo: alguns a cada 1%, outros a cada 10% ou mais. Com o padrão de 10 pontos, dispositivos com passos de 10% alertam a cada passo. Se o mesmo dispositivo disparar bateria fraca na mesma verificação, só esse alerta é emitido.

### Dispositivo conecta e dispositivo desconecta

Desativados por padrão. Alertam na mudança entre conectado e desconectado. Como no tempo conectado, considera-se conectado salvo quando se sabe que está desconectado. Assim, LE (status desconhecido) só alerta desconexão quando o Windows o informa como desconectado. A primeira verificação após iniciar o NVDA apenas memoriza o estado. As demais ocorrem a cada poucos segundos (veja configurações).

### Estojo de recarga

Para fones totalmente sem fio com estojo. Desativado por padrão, por dispositivo. O Windows informa a bateria dos fones, não do estojo; o complemento estima quantas vezes o estojo os carregou. **Estojo de recarga...** no menu Alertas abre:

- **Alertar sobre o estojo de recarga** — Ativa estimativa e alerta.
- **Autonomia dos fones por recarga (horas)** e **Autonomia total com o estojo (horas)** — Por exemplo, 10 e 52 horas. O estojo pode então recarregar cerca de 4,2 vezes: 52 dividido por 10, menos a carga inicial dos próprios fones.
- **Usar estatísticas** — Preenche a autonomia por carga com a estimativa de carga completa, arredondada para meia hora.
- **Alertar quando restarem menos recargas que** — Padrão 1.

A cada recarga observada dos fones, os pontos ganhos são somados às recargas usadas (100 pontos equivalem a uma carga). O alerta ocorre quando os fones estão fracos, no nível próprio ou padrão, e a estimativa restante do estojo fica abaixo do campo acima. É hora de carregar ambos. Alerta uma vez até a recuperação da bateria e mostra aviso como o de bateria fraca.

Depois do alerta, ao observar a próxima recarga dos fones (retirados do estojo e conectados), o complemento pergunta se você também carregou o estojo. **Sim** reinicia a contagem do zero. **Não**, a resposta padrão, continua contando.

A qualquer momento, use **Marcar estojo como carregado** (Control+Shift+R nas estatísticas) para reiniciar. A cada marcação, o complemento lembra quantas recargas o estojo forneceu naquela rodada. A partir da terceira rodada concluída, usa o valor típico das últimas cinco no lugar das autonomias informadas.

Limites da estimativa:

- Funciona bem apenas se os fones forem usados principalmente neste computador. Recargas enquanto usados com outro dispositivo, como celular, não contam; o estojo parece mais cheio que o real.
- É preciso informar cada recarga do estojo, respondendo ou marcando, pois o complemento não pode saber.
- O tempo conectado precisa ser medido, como nas estatísticas.
- É uma estimativa, não uma medição.

### Sons dos alertas

A fala anuncia, por exemplo, “nome do dispositivo conectado” ou “nome do dispositivo bateria 80%”; os dois bipes são iguais em todos os alertas; o som próprio é um arquivo .wav da pasta `sounds` do complemento (ao lado de `globalPlugins`). Use **Abrir pasta de sons...** e substitua um arquivo para mudar o som. Se faltar, toca um bipe. Vários alertas tocam em sequência. Arquivos:

- `lowBattery.wav`
- `levelDrop.wav`
- `deviceConnected.wav`
- `deviceDisconnected.wav`
- `chargingCase.wav`

## Monitoramento em segundo plano

Quando o alerta de bateria fraca, o acompanhamento do tempo ou algum alerta de dispositivo está ativo, verifica a bateria a cada 5 minutos. Enquanto houver alerta de conexão ou desconexão, verifica conexões mais frequentemente (a cada poucos segundos, veja configurações); o restante continua a cada 5 minutos.

## Dados e configurações

Os registros ficam em `btBatterytics_usage.json`, na pasta de configuração do usuário do NVDA. Copie esse arquivo para fazer backup. Exclua-o com o NVDA fechado para recomeçar.

Na primeira execução, o BT-Batterytics incorpora o que foi salvo no nome anterior: copia registros de `blueToothBatteryReport_usage.json` (preservando o original) e usa a antiga seção de configurações. Registros anteriores à identificação por endereço migram para o endereço do dispositivo de mesmo nome na primeira detecção.

## Créditos dos sons

Os sons incluídos são do Pixabay:

- `levelDrop.wav` — Efeito por [Vadim](https://pixabay.com/users/vadim_makes_sound-54823268/?utm_source=link-attribution&utm_medium=referral&utm_campaign=music&utm_content=614159), do [Pixabay](https://pixabay.com/sound-effects/?utm_source=link-attribution&utm_medium=referral&utm_campaign=music&utm_content=614159)
- `lowBattery.wav` — Efeito por [Shagor Miah](https://pixabay.com/users/u_31vnwfmzt6-31480456/?utm_source=link-attribution&utm_medium=referral&utm_campaign=music&utm_content=126627), do [Pixabay](https://pixabay.com/sound-effects/?utm_source=link-attribution&utm_medium=referral&utm_campaign=music&utm_content=126627)
- `deviceConnected.wav` — Efeito por [juniorsoundays](https://pixabay.com/users/juniorsoundays-19205462/?utm_source=link-attribution&utm_medium=referral&utm_campaign=music&utm_content=527856), do [Pixabay](https://pixabay.com/sound-effects/?utm_source=link-attribution&utm_medium=referral&utm_campaign=music&utm_content=527856)
- `deviceDisconnected.wav` — Efeito por [juniorsoundays](https://pixabay.com/users/juniorsoundays-19205462/?utm_source=link-attribution&utm_medium=referral&utm_campaign=music&utm_content=527837), do [Pixabay](https://pixabay.com/sound-effects/?utm_source=link-attribution&utm_medium=referral&utm_campaign=music&utm_content=527837)

## Créditos e licença

O BT-Batterytics é baseado no [BlueToothBatteryReport](https://github.com/haitun001/BlueToothBatteryReport), Copyright (C) haitun001 e cary-rowen, modificado em 2026 por NVDATH. É coberto pela GNU General Public License versão 2, como o original.

### Como as modificações foram feitas

As ideias, decisões sobre o comportamento e todos os testes com NVDA foram realizados por NVDATH. Todas as modificações do código original foram escritas por Claude, assistente de IA da Anthropic, seguindo suas instruções. O código não foi escrito manualmente por um programador; informe qualquer problema a NVDATH.

## Versões do NVDA compatíveis

- Mínima: `2025.1.0`
- Testado até: `2026.3.1`

