# Ambiente Portátil de Aprendizado com IA — Design

## Objetivo

Criar um repositório local, independente de fornecedor, que transforme agentes
de IA em tutores para matemática e fundamentos/frameworks de IA. O sistema se
baseia no método encontrado em `amosblomqvist/learn` para o Pi, mas separa a
pedagogia das ferramentas específicas de cada agente.

O primeiro release deve funcionar com Cursor, Claude Code e Pi, além de
oferecer uma entrada genérica por `AGENTS.md`. Não haverá aplicação própria,
banco de dados, API ou dependência obrigatória além de Markdown e Python 3 para
validação.

## Princípios

1. A pedagogia possui uma única fonte de verdade.
2. Adaptadores traduzem capacidades; não duplicam o método.
3. Conhecimento é organizado como um grafo de pré-requisitos e conclusões.
4. O tutor mede compreensão por aplicação, não por repetição.
5. Afirmações matemáticas explicitam hipóteses; fatos atuais sobre frameworks
   exigem verificação por fonte quando houver acesso à web.
6. Toda capacidade opcional possui uma degradação conversacional.
7. Dados pessoais de estudo permanecem locais e fora do Git por padrão.

## Arquitetura

### Núcleo canônico

`core/` contém instruções independentes de agente:

- `pedagogy.md`: princípios de conhecimento conectado, derivação motivada e
  aprendizagem ativa.
- `session-protocol.md`: ciclo completo de uma sessão.
- `assessment.md`: diagnóstico adaptativo, construção de perguntas e critérios
  de domínio.
- `evidence-policy.md`: quando pesquisar, como citar, como marcar incerteza e
  como tratar hipóteses matemáticas.

O núcleo não menciona nomes de ferramentas proprietárias.

### Entradas e adaptadores

`AGENTS.md` é a entrada universal e orienta qualquer agente compatível a ler o
núcleo, o perfil local e a trilha escolhida.

`adapters/` contém notas específicas para Cursor, Claude Code e Pi. Cada
adaptador mapeia quatro capacidades:

- pergunta/quiz;
- pesquisa e verificação;
- visualização;
- persistência da sessão.

`.cursor/skills/learning-tutor/SKILL.md` torna o tutor descobrível no Cursor.
Ele referencia o núcleo em vez de reproduzi-lo. O adaptador Claude Code fornece
uma entrada compatível com suas instruções de projeto. O adaptador Pi fornece
um skill instalável e explica como integrar extensões opcionais.

### Trilhas iniciais

`curricula/mathematics/` e `curricula/ai/` contêm mapas pequenos e editáveis,
não cursos fechados.

A trilha de matemática cobre inicialmente:

- álgebra e funções;
- cálculo;
- álgebra linear;
- probabilidade e estatística;
- matemática para aprendizado de máquina.

A trilha de IA cobre inicialmente:

- fundamentos de aprendizado de máquina;
- redes neurais;
- transformers e LLMs;
- avaliação e experimentação;
- uso consciente de frameworks.

Cada mapa declara resultados observáveis, pré-requisitos, conceitos e projetos
de aplicação. O tutor seleciona somente o caminho relevante ao objetivo atual.

### Estado privado

`templates/` versiona modelos para perfil do aluno, objetivo, log de sessão e
progresso. `workspace.example/` demonstra o layout preenchido com dados
fictícios. `workspace/` guarda os dados reais e é ignorado pelo Git.

O progresso registra evidências observáveis: questão resolvida, explicação
produzida, implementação concluída ou erro diagnosticado. Não usa somente
rótulos vagos como "estudado" ou "entendido".

## Protocolo pedagógico

### 1. Definir resultado

Converter o interesse inicial em um resultado verificável. Exemplo: trocar
"aprender transformers" por "explicar self-attention e implementar uma versão
mínima usando operações tensoriais".

### 2. Diagnosticar

Mapear apenas os pré-requisitos relevantes. Para cada ramo, encontrar um piso
demonstrado e uma lacuna ou limite. O diagnóstico usa saltos de dificuldade e
tem limite padrão para evitar interrogatório excessivo. O aluno pode pedir um
diagnóstico mais curto ou mais profundo.

### 3. Planejar

Apresentar:

- objetivo operacional;
- conceitos necessários em ordem de dependência;
- conhecimentos já demonstrados;
- lacunas que serão trabalhadas;
- critério de conclusão.

O aluno aprova ou ajusta o plano antes da aula.

### 4. Ensinar

Cada conceito passa pelo mesmo ciclo:

1. motivar por que ele é necessário agora;
2. estabelecer ou derivar a ideia a partir do que já está firme;
3. explicitar a conexão com os nós anteriores;
4. verificar por pergunta, derivação, previsão ou pequena aplicação.

Uma resposta errada aciona feedback direcionado à hipótese incorreta e uma nova
tentativa. Uma sequência de respostas corretas aumenta a dificuldade ou passa
para transferência, em vez de repetir exercícios equivalentes.

### 5. Encerrar

Produzir resumo, evidências demonstradas, lacunas remanescentes e próximo passo.
Se houver persistência, atualizar os arquivos privados. Caso contrário,
entregar um bloco Markdown pronto para salvar.

## Política de evidências

Afirmações matemáticas devem informar domínio, hipóteses e se são definição,
teorema, consequência ou aproximação. O tutor pode derivá-las diretamente
quando a derivação for verificável.

Informações voláteis — versões, APIs, benchmarks, preços, suporte de hardware e
comportamento atual de frameworks — devem ser confirmadas em documentação
primária quando houver web. Sem web, o tutor declara a limitação e evita
apresentar memória potencialmente desatualizada como fato.

Fontes primárias e documentação oficial têm prioridade. Uma citação deve apoiar
a afirmação adjacente, não apenas aparecer numa bibliografia genérica.

## Degradação de capacidades

- Sem quiz estruturado: fazer uma pergunta por vez em conversa normal.
- Sem subagentes: pesquisar e ensinar sequencialmente no agente principal.
- Sem web: marcar fatos atuais como não verificados e priorizar conteúdo
  estável.
- Sem renderização: usar Mermaid quando suportado ou uma lista textual de
  dependências.
- Sem escrita em disco: devolver os registros como blocos Markdown.
- Sem memória entre sessões: começar lendo um resumo fornecido pelo usuário.

Nenhuma ausência de ferramenta impede o método central.

## Estrutura de arquivos

```text
.
├── README.md
├── AGENTS.md
├── core/
│   ├── pedagogy.md
│   ├── session-protocol.md
│   ├── assessment.md
│   └── evidence-policy.md
├── curricula/
│   ├── mathematics/
│   └── ai/
├── templates/
│   ├── learner-profile.md
│   ├── learning-goal.md
│   ├── session-log.md
│   └── progress.md
├── adapters/
│   ├── cursor/
│   ├── claude-code/
│   └── pi/
├── .cursor/skills/learning-tutor/
├── workspace.example/
├── workspace/
├── tests/
│   └── validate_repository.py
└── docs/superpowers/
    ├── specs/
    └── plans/
```

## Validação

`tests/validate_repository.py` usa somente a biblioteca padrão do Python e
falha quando:

- um arquivo obrigatório está ausente;
- um link Markdown interno aponta para arquivo inexistente;
- um skill possui frontmatter inválido ou nome incompatível;
- um adaptador duplica blocos canônicos marcados;
- `workspace/` não está ignorado;
- dados privados conhecidos aparecem entre arquivos rastreados.

O teste deve funcionar em Windows, macOS e Linux, usando `pathlib` e caminhos
com `/` na documentação.

## Fora do escopo inicial

- interface gráfica;
- servidor ou banco de dados;
- chamadas diretas a APIs de modelos;
- sincronização em nuvem;
- geração automática dos adaptadores;
- currículo completo;
- sistema próprio de flashcards ou repetição espaçada.

Esses itens só serão considerados após uso real demonstrar a necessidade.

## Critérios de aceitação

1. Um agente genérico consegue iniciar uma sessão lendo `AGENTS.md`.
2. Cursor, Claude Code e Pi encontram instruções próprias sem duplicar o núcleo.
3. O mesmo objetivo gera o ciclo definir, diagnosticar, planejar, ensinar e
   encerrar nos três adaptadores.
4. O repositório inclui trilhas iniciais úteis de matemática e IA.
5. Dados reais do aluno não são adicionados ao Git por padrão.
6. O validador passa em uma cópia limpa do repositório.
7. O README explica instalação, uso, portabilidade e limitações.
