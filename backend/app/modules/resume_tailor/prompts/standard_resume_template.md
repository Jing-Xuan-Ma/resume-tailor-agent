# Standard Resume Template v1

This is the fixed resume format for all generated drafts and exports.

## Reference Layout

XXXXXXX XX
+1 (XXX) XXX-XXXX | xxxxxxx@xxxxx.xxx | LinkedIn | Portfolio
Data Science M.S. student at Johns Hopkins with a background in Applied Statistics and data analytics. Skilled in R, advanced SQL, Python ETL pipelines using Apache Airflow, Tableau dashboard development, operations automation, stakeholder collaboration, and AI prompt engineering to accelerate data analysis.

EDUCATION
Johns Hopkins University August 2025 - June 2027
Master of Science in Data Science Baltimore, US
* Coursework: Database Systems | Introduction to Algorithms | Nonlinear Optimization | Human-Computer Interaction

PROFESSIONAL EXPERIENCE
Data Analyst Intern | XXXXXXX Securities Co., Ltd. Beijing, China | June 2024 - August 2024
* Faced with the need to evaluate whether a pricing model library could meet both runtime and maintainability requirements, conducted a structured feasibility analysis across Python, pure & optimized C++, Eigen vectorization, OpenMP, and ctypes-based Python/C++ integration
* Built and benchmarked a 100,000-path Monte Carlo pricing simulation, applying compiler optimization, vectorized matrix operations, and multithreaded random-path generation to isolate major bottlenecks in computation-intensive pricing workflows
* Delivered a hybrid architecture recommendation that assigned heavy simulation and statistical computation to C++ while keeping configuration, preprocessing, and visualization in Python; reduced runtime from approx. 33.4s to approx. 1.4s with OpenMP optimization

PROJECTS
Credit Risk Prediction Model | Python, SQL, scikit-learn, XGBoost, R Independent Project
* To build and adapt algorithms for complex risk use cases, designed an end-to-end predictive pipeline integrating SQL-style extraction, missing-value treatment, feature engineering, and statistical modeling to estimate expected claim costs and credit default behavior
* Applied advanced statistics and machine learning libraries (scikit-learn, XGBoost) to train, evaluate, and benchmark regression and tree-based models, leveraging ROC-AUC, F1-score, and cost drivers to balance predictive accuracy with business interpretability
* Extended the framework with stochastic modeling via Monte Carlo simulations to analyze skewed loss distributions, interpreting error patterns to translate quantitative outputs into risk-monitoring thresholds and optimized decision-making insights

COMPETITIONS
Mathematical Contest in Modeling | Team Leader Remote | February 2023
* Led a student modeling team through problem scoping, data cleaning, indicator screening, visualization, model development, and technical report writing, coordinating responsibilities to deliver a structured solution under time constraints

SKILLS & CERTIFICATIONS
Python, R, SQL, C, C++, SPSS; data cleaning, feature engineering, exploratory analysis, technical documentation, Pandas, NumPy, scikit-learn, XGBoost, matplotlib; regression, classification, predictive modeling, model evaluation, visualization, probability, regression analysis, hypothesis testing, optimization, model validation, performance benchmarking, business insight translation, Actuarial Science, Financial Modeling, Pricing Model Analysis, Risk Analytics, Credit Risk, Claims Modeling, Monte Carlo Simulation, Apache Airflow, Tableau.

## Strict Rules

Canonical policy: repository root `RESUME_CONSTITUTION.md` (wins on conflict).

1. Single-page layout. Header is centered: bold name, then one contact line separated by ` | `.
2. Summary is a paragraph of no more than 3 lines. It has no section title and appears immediately after contact.
3. Section order is fixed: EDUCATION, PROFESSIONAL EXPERIENCE, PROJECTS, COMPETITIONS, SKILLS & CERTIFICATIONS. Omit empty sections, but never reorder.
4. Section headings are uppercase and bold.
5. Entry heading format: `[Name] | [Tools/Company] — [City/Context] — [Date]`. In Word/PDF, the date should visually align right when possible.
6. Master inventory entries default to 3 bullets. Delivery projections may hide whole entries or compress to 2 bullets to fit one page and match the JD; never invent new entries.
7. Each bullet follows situation-action-result: start with context/goal, describe concrete action with a strong verb, end with evidence-backed result/impact when the source supports it.
8. Skills are a comma/semicolon-separated keyword string, never bullet points. Reorder/subset by JD; do not dump the full inventory every time.
9. Do not fabricate tools, numbers, companies, titles, dates, degrees, certifications, project scope, or outcomes.
10. Before final output, self-check whether the result fits one page, avoids fabrication, and follows every format rule above and `RESUME_CONSTITUTION.md`.
11. **ATS text hygiene (mandatory):** never use arrows or decorative symbols (`→ ← ⇒ • ★ ✓` etc.) in any resume field. Use commas, `|`, hyphens, or words (`to`, `then`). Keep inventory technical terms verbatim.
12. **Verb variety:** within one experience, use different strong verbs across bullets (Built / Designed / Delivered / Integrated / Optimized) so capability layers are visible.
13. **One-page cuts:** prefer hiding overlapping projects (same methods/tools/domain) over deleting verified internships or unique projects.
14. Experience headings: title|company may be bold in Word; location|dates must remain regular weight (content JSON should not try to restyle).
