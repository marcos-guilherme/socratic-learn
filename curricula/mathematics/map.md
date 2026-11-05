# Starter Mathematics Curriculum

This map is a compact, editable dependency guide rather than a complete course.
Mathematical claims follow the [evidence policy](../../core/evidence-policy.md):
state the domain and hypotheses, and distinguish definitions, theorems,
consequences, approximations, heuristics, and empirical observations.

### algebraic-reasoning — Algebraic reasoning

- Outcome: Solve a one-variable equation and justify each equivalence-preserving step.
- Prerequisites: none
- Concepts: variables and expressions; equality and equivalence; for real \(a,b,c\) with \(a\ne0\), \(ax+b=c\iff x=(c-b)/a\) (exact consequence of field operations)
- Evidence: Over \(\mathbb R\), solve the exact equation \(3(x-2)=15\), then verify the result by substitution and explain why each equivalence preserves the solution set.
- Application: Express a fixed-fee-plus-unit-cost budget as an equation and compute the affordable quantity.

### functions-and-graphs — Functions and graphs

- Outcome: Define a function's domain and codomain and connect a formula, table, and graph for the same relation.
- Prerequisites: algebraic-reasoning
- Concepts: function as a single-valued mapping (definition); domain, codomain, and range; composition; graph and rate of change
- Evidence: For the example defined by \(f:\mathbb R\to\mathbb R\), \(f(x)=2x-1\), produce a value table, sketch the graph, and recover the slope and intercept.
- Application: Model a temperature conversion or linear pricing rule and identify which inputs are meaningful.

### limits-and-change — Limits and change

- Outcome: Estimate a limit numerically and graphically, then verify a simple limit from its definition or limit laws.
- Prerequisites: functions-and-graphs
- Concepts: local behavior; one-sided and two-sided limits; for \(f:\mathbb R\to\mathbb R\), \(\lim_{x\to a}f(x)=L\) under the epsilon-delta condition (definition); continuity at a point
- Evidence: For real \(x\ne2\), derive the exact consequence \(\lim_{x\to2}(x^2-4)/(x-2)=4\) from algebra and limit laws, and state why the original value at \(2\) is irrelevant.
- Application: Estimate an instantaneous trend from measurements taken over successively shorter time intervals.

### derivatives — Derivatives

- Outcome: Compute and interpret a derivative while naming the domain and differentiability assumptions.
- Prerequisites: limits-and-change
- Concepts: for \(f:\mathbb R\to\mathbb R\), \(f'(a)=\lim_{h\to0}[f(a+h)-f(a)]/h\) when the limit exists (definition); tangent slope; derivative rules; differentiability implies continuity at the point (theorem)
- Evidence: For \(f:\mathbb R\to\mathbb R\), \(f(x)=x^2\), derive the exact identity \(f'(x)=2x\) from the derivative definition and compare it with secant slopes near a chosen point.
- Application: Determine the marginal change of a quadratic cost or position model at a specified input.

### vectors-and-dot-products — Vectors and dot products

- Outcome: Compute a dot product and use it to test orthogonality or compare directions.
- Prerequisites: algebraic-reasoning
- Concepts: vectors in \(\mathbb R^n\); linear combination; \(u\cdot v=\sum_{i=1}^{n}u_iv_i\) for \(u,v\in\mathbb R^n\) (definition); norm and angle, with nonzero vectors required for cosine similarity
- Evidence: For two vectors in \(\mathbb R^3\), compute their dot product, norms, and cosine similarity and check the result against geometric expectations.
- Application: Rank two small feature vectors by directional similarity.

### matrices-and-linear-maps — Matrices and linear maps

- Outcome: Apply a matrix to a vector and explain the associated linear transformation.
- Prerequisites: vectors-and-dot-products
- Concepts: matrix dimensions; matrix-vector multiplication; \(T(x)=Ax\) for \(A\in\mathbb R^{m\times n}\), \(x\in\mathbb R^n\) (definition of the represented linear map); composition and change of coordinates
- Evidence: Multiply a \(2\times2\) matrix by basis vectors and use the images to predict and verify its action on another vector.
- Application: Implement a two-dimensional scaling, reflection, or rotation and test it on three points.

### probability-models — Probability models

- Outcome: Construct a finite probability model and calculate event probabilities without double counting.
- Prerequisites: algebraic-reasoning
- Concepts: sample space and events; probability measure (definition); for disjoint events \(A,B\), \(P(A\cup B)=P(A)+P(B)\) (axiom consequence); conditional probability where the conditioning event has positive probability
- Evidence: Define a complete sample space for two coin tosses and compute a union and a conditional probability from it.
- Application: Model a small reliability, screening, or game scenario and state the assumptions behind its probabilities.

### random-variables — Random variables

- Outcome: Derive the distribution, expectation, and variance of a finite discrete random variable.
- Prerequisites: probability-models, functions-and-graphs
- Concepts: random variable as a measurable function (definition); probability mass function; for finite discrete \(X\), \(E[X]=\sum_x xP(X=x)\) (exact definition in this setting); variance \(E[(X-E[X])^2]\) when the expectation is finite (definition)
- Evidence: Build the distribution of the number of heads in two fair independent tosses and compute its expectation and variance.
- Application: Compare the expected value and variability of two simple decisions with uncertain payoffs.

### optimization — Optimization

- Outcome: Find and check candidate optima for a differentiable one-variable objective or a small unconstrained multivariable objective.
- Prerequisites: derivatives, vectors-and-dot-products
- Concepts: objective and feasible set; local and global optima; if differentiable \(f:\mathbb R^n\to\mathbb R\) has an unconstrained local optimum at an interior point \(x^\*\), then \(\nabla f(x^\*)=0\) (necessary-condition theorem); convexity
- Evidence: Minimize a quadratic objective, verify the stationary point, and distinguish the necessary first-order condition from sufficient curvature evidence.
- Application: Tune one parameter to minimize a measured or analytic error function.

### math-for-machine-learning — Mathematics for machine learning

- Outcome: Trace dimensions and assumptions through a small linear prediction model and one optimization update.
- Prerequisites: matrices-and-linear-maps, random-variables, optimization
- Concepts: for \(X\in\mathbb R^{m\times n}\), \(w\in\mathbb R^n\), predictions \(Xw\in\mathbb R^m\) (exact dimensional consequence); loss as an objective; distributional expectation versus finite-sample average; gradient update \(w_{t+1}=w_t-\eta\nabla L(w_t)\) for \(\eta>0\) (algorithm definition, not a convergence guarantee)
- Evidence: Compute predictions, mean squared error, and one gradient step for a two-example linear model while checking every dimension.
- Application: Implement the calculation in a spreadsheet or short script and explain which assumptions would fail on new data.
