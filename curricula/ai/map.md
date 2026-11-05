# Starter AI Curriculum

This map is a compact, editable dependency guide rather than a complete course.
The `Prerequisites` field names only nodes in this file; mathematical
dependencies are explicit links below and within relevant concepts.

## Mathematics prerequisites

Use the mathematics map to select only the dependencies needed for the target:
[functions and graphs](../mathematics/map.md#functions-and-graphs),
[exponentials and logarithms](../mathematics/map.md#exponentials-and-logarithms),
[vectors and dot products](../mathematics/map.md#vectors-and-dot-products),
[matrices and linear maps](../mathematics/map.md#matrices-and-linear-maps),
[probability models](../mathematics/map.md#probability-models),
[random variables](../mathematics/map.md#random-variables),
[optimization](../mathematics/map.md#optimization), and the integrated
[mathematics for machine learning](../mathematics/map.md#math-for-machine-learning)
node.

Framework APIs, versions, defaults, compatibility, and hardware support are
volatile. Verify consequential claims against current primary documentation
and record version or date context according to the
[evidence policy](../../core/evidence-policy.md).

### supervised-learning — Supervised learning

- Outcome: Frame a labeled prediction problem by specifying examples, targets, model output, and an observable success criterion.
- Prerequisites: none
- Concepts: training examples and labels; features and targets; hypothesis or model; empirical risk, using [functions and graphs](../mathematics/map.md#functions-and-graphs) and [random variables](../mathematics/map.md#random-variables)
- Evidence: Convert a small real-world question into a five-row dataset schema and identify the input, target, prediction unit, and possible leakage.
- Application: Define a baseline predictor for a small classification or regression dataset.

### loss-and-generalization — Loss and generalization

- Outcome: Compute a loss on held-out examples and explain why training performance alone does not establish generalization.
- Prerequisites: supervised-learning
- Concepts: per-example and aggregate loss; train-validation-test roles; overfitting and underfitting; sampling uncertainty grounded in [probability models](../mathematics/map.md#probability-models)
- Evidence: Calculate training and validation error for two candidate predictors and defend a selection while naming limits of the evidence.
- Application: Design a small data split and a comparison against a constant or majority-class baseline.

### gradient-based-learning — Gradient-based learning

- Outcome: Execute one gradient-based parameter update and measure whether the selected loss changed.
- Prerequisites: loss-and-generalization
- Concepts: parameterized objective; gradients and learning rate from [optimization](../mathematics/map.md#optimization); batch and stochastic estimates; convergence claims require stated assumptions and evidence
- Evidence: For a one-parameter quadratic loss, derive the gradient, perform one update, and compare the loss before and after.
- Application: Fit a one-feature linear predictor for several steps and plot or tabulate the loss trajectory.

### neural-networks — Neural networks

- Outcome: Trace dimensions and compute a forward pass through a small feed-forward network.
- Prerequisites: gradient-based-learning
- Concepts: affine layers using [matrices and linear maps](../mathematics/map.md#matrices-and-linear-maps); nonlinear activation; composition and computational graph; backpropagation as structured chain-rule evaluation
- Evidence: Compute every intermediate value and shape for a two-input, two-hidden-unit, one-output network.
- Application: Implement the forward pass with basic array operations and compare it with a hand calculation.

### tensor-frameworks — Tensor frameworks

- Outcome: Reproduce a hand-checked tensor computation in one framework and verify values, shapes, and gradients.
- Prerequisites: neural-networks
- Concepts: tensors and broadcasting; automatic differentiation; device and dtype semantics; APIs and hardware behavior are volatile under the [evidence policy](../../core/evidence-policy.md)
- Evidence: Run a matrix operation and scalar loss, inspect the resulting shapes and gradient, and record the framework version and device context.
- Application: Build a minimal training step whose numerical result can be checked independently.

### attention — Attention

- Outcome: Compute scaled dot-product attention for a tiny example and explain how changing one score changes the output weights.
- Prerequisites: neural-networks
- Concepts: query, key, and value projections; dot products from [vectors and dot products](../mathematics/map.md#vectors-and-dot-products); exponentials in softmax from [exponentials and logarithms](../mathematics/map.md#exponentials-and-logarithms); softmax-normalized weights; masking
- Evidence: Calculate all scores, normalized weights, and the weighted output for one query and two key-value pairs.
- Application: Create a toy retrieval example and predict the effect of modifying one key before recomputing it.

### transformers — Transformers

- Outcome: Trace tensor shapes and information flow through a minimal transformer block.
- Prerequisites: attention, tensor-frameworks
- Concepts: multi-head attention; residual connections and normalization; position information; feed-forward sublayer
- Evidence: Annotate the shape of every tensor in a one-layer, two-token transformer block and verify one residual path.
- Application: Implement or adapt a tiny block and test that sequence length and feature dimensions match the annotated design.

### language-models — Language models

- Outcome: Formulate next-token prediction and evaluate the probabilities assigned to a short token sequence.
- Prerequisites: transformers
- Concepts: tokenization; conditional next-token distribution; cross-entropy and log loss grounded in [exponentials and logarithms](../mathematics/map.md#exponentials-and-logarithms); generation as a policy over successive conditional distributions
- Evidence: Given explicit token probabilities, compute sequence log loss and explain how one probability affects the total.
- Application: Compare greedy selection and sampled selection on a supplied probability table without claiming behavior beyond the example.

### evaluation — Evaluation

- Outcome: Design and execute a small evaluation whose metric, dataset, failure categories, and uncertainty match a stated use.
- Prerequisites: loss-and-generalization
- Concepts: construct and metric validity; baselines and slices; qualitative error analysis; uncertainty and distribution shift using [probability models](../mathematics/map.md#probability-models)
- Evidence: Score two systems on a fixed example set, inspect disagreements, and report at least one metric limitation and one unresolved uncertainty.
- Application: Create a reusable evaluation card for a classifier or regressor, or specialize it for a language model when that is the chosen system.

### framework-experimentation — Framework experimentation

- Outcome: Run a reproducible framework experiment and separate stable algorithmic conclusions from volatile implementation observations.
- Prerequisites: tensor-frameworks, evaluation
- Concepts: controlled comparison; seeds, environment, and dependency records; profiling and numerical checks; API, version, and hardware claims require current primary evidence under the [evidence policy](../../core/evidence-policy.md)
- Evidence: Change one factor in a minimal experiment, capture commands and environment versions, and compare outputs against a framework-independent expectation.
- Application: Maintain a small experiment log that another learner can rerun and use to challenge one implementation claim.
