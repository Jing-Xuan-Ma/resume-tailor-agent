"""
简历定制质量检测脚本

用两份差异极大的 JD 对同一份简历进行定制，比较输出的差异。
以此验证系统是否真正根据 JD 和用户简历生成定制化内容。

使用方法：
  1. 确保后端已启动：uvicorn app.main:app --reload
  2. python test_quality_check.py
"""

import requests
import json

BASE = "http://127.0.0.1:8000/api/v1/resume-tailor"
USER_ID = "00000000-0000-0000-0000-000000000001"
RESUME_ID = "00000000-0000-0000-0000-000000000002"

# =============================================================================
# JD 1: 量化风险分析师 / 精算分析师 (与简历强相关)
# =============================================================================
JD_RISK = """Quantitative Risk Analyst - Insurance & Financial Services

About the Role:
Join our quantitative risk team to develop and maintain pricing and risk models for insurance and investment products. You will work on loss reserving, capital modeling, and pricing framework optimization.

Responsibilities:
- Develop and maintain actuarial pricing models using Python and R for insurance products across multiple lines of business
- Perform loss distribution analysis, reserve estimation, and capital adequacy assessment using stochastic modeling techniques
- Build Monte Carlo simulation frameworks to evaluate tail risk, stress scenarios, and capital requirements under IFRS 17 and Solvency II
- Analyze claims severity and frequency data; engineer exposure- and policy-level features for GLM and tree-based pricing models
- Validate and benchmark pricing model libraries for runtime performance and statistical accuracy
- Translate quantitative model outputs into risk-monitoring thresholds, pricing recommendations, and portfolio-level reports
- Collaborate with underwriting, finance, and product teams to align risk models with business strategy
- Maintain documentation for model governance, validation, and regulatory compliance

Requirements:
- M.S. or B.S. in Actuarial Science, Statistics, Mathematics, Data Science, or related quantitative field
- 2+ years experience in actuarial modeling, risk analytics, or quantitative pricing (internship experience counts)
- Strong proficiency in Python (pandas, numpy, scikit-learn) and R for statistical modeling and simulation
- Solid understanding of probability theory, regression analysis, hypothesis testing, and loss distribution modeling
- Experience with Monte Carlo simulation, stochastic processes, and scenario analysis
- Knowledge of GLM, decision trees, and ensemble methods for pricing and risk models
- SQL proficiency for data extraction and feature engineering
- Strong written and verbal communication skills for presenting quantitative findings to non-technical stakeholders

Preferred:
- Progress toward actuarial credentials (SOA/CAS exams)
- Experience with IFRS 17, Solvency II, or C-ROSS regulatory frameworks
- Familiarity with C++ for performance-critical pricing computations
- Experience with Tableau or similar visualization tools for risk reporting
- Knowledge of credit risk modeling, expected loss estimation, and portfolio credit risk
"""

# =============================================================================
# JD 2: 数据平台工程师 / MLOps 工程师 (与简历差异极大)
# =============================================================================
JD_MLOPS = """Data Platform Engineer - MLOps & Infrastructure

About the Role:
We are building a scalable data platform to serve machine learning workloads across the organization. We need an engineer who can own the infrastructure that trains, deploys, and monitors models in production — from data ingestion pipelines to model serving endpoints.

Responsibilities:
- Design and maintain CI/CD pipelines for ML model training and deployment using GitHub Actions, Jenkins, or GitLab CI
- Containerize ML training and inference workloads using Docker and orchestrate with Kubernetes (K8s) on AWS EKS or GCP GKE
- Build and manage feature stores (Feast, Tecton) and model registries (MLflow, Weights & Biases) for production ML workflows
- Implement data pipeline monitoring, alerting, and observability using Prometheus, Grafana, and ELK stack
- Optimize distributed data processing workflows using Apache Spark, Ray, or Dask for large-scale training datasets
- Manage cloud infrastructure as code using Terraform or Pulumi across AWS/GCP environments
- Set up A/B testing infrastructure and model canary deployments with traffic splitting and automated rollback
- Ensure platform reliability through SLO/SLI definition, incident response, and post-mortem analysis
- Automate GPU cluster scheduling, resource allocation, and cost tracking for training jobs

Requirements:
- 3+ years experience in data engineering, platform engineering, or MLOps roles
- Deep knowledge of Docker and Kubernetes in production — pod lifecycle, Helm charts, service mesh (Istio/Linkerd)
- Strong experience with CI/CD tooling (GitHub Actions, ArgoCD, or similar) and infrastructure-as-code (Terraform)
- Proficiency in Python for scripting, automation, and building data/ML platform tooling
- Hands-on experience with cloud platforms — AWS (ECS, EKS, S3, Lambda) or GCP (GKE, Cloud Run, BigQuery)
- Experience building and maintaining ETL/ELT pipelines at scale (Spark, Airflow, or similar orchestrators)
- Understanding of ML lifecycle: experiment tracking, model versioning, online/offline serving, monitoring drift
- Strong Linux systems knowledge: shell scripting, networking, process management, filesystem

Preferred:
- Experience with GPU orchestration (NVIDIA GPU Operator, CUDA compatibility, multi-GPU training setups)
- Contributions to open-source MLOps or data infrastructure projects
- Knowledge of streaming data (Kafka, Kinesis, Flink) and real-time feature computation
- Experience with LLM serving infrastructure (vLLM, TensorRT-LLM, Triton Inference Server)
- Understanding of data governance, lineage, and catalog tools (Apache Atlas, DataHub, Amundsen)
"""

# =============================================================================
# 测试函数
# =============================================================================

def test_upload_resume():
    print("=" * 60)
    print("1. 上传简历")
    print("=" * 60)
    # 用简历文本内容
    resume_text = open("test_resume.txt", encoding="utf-8").read()
    r = requests.post(f"{BASE}/upload-resume", json={
        "user_id": USER_ID,
        "resume_text": resume_text
    })
    print(f"  状态码: {r.status_code}")
    print(f"  响应: {r.json()}")
    print()
    return r.json()


def test_tailor(jd_label, jd_text):
    print("=" * 60)
    print(f"2. 定制简历 — {jd_label}")
    print("=" * 60)

    r = requests.post(f"{BASE}/tailor", json={
        "user_id": USER_ID,
        "resume_id": RESUME_ID,
        "jd_text": jd_text,
    })

    print(f"  状态码: {r.status_code}")
    if r.status_code != 200:
        print(f"  错误: {r.text}")
        return None

    result = r.json()
    tr = result.get("tailored_resume", {})

    print(f"  成功: {result.get('success')}")
    print(f"  定制摘要: {(tr.get('tailoring_summary') or '')[:300]}")
    print(f"  ATS 评分: {tr.get('ats_score_estimate')}")
    print(f"  技能数量: {len(tr.get('skills', []))}")
    print(f"  工作经历数: {len(tr.get('experiences', []))}")
    print(f"  项目数: {len(tr.get('projects', []))}")
    print(f"  教育数: {len(tr.get('education', []))}")

    skills = tr.get("skills", [])
    if skills:
        print(f"\n  定制技能:")
        for s in skills:
            print(f"    - {s}")

    for exp in tr.get("experiences", []):
        print(f"\n  📌 {exp.get('title')} @ {exp.get('company')} ({exp.get('date_range')})")
        for b in exp.get("bullets", []):
            print(f"    ▸ {b.get('text', '')[:120]}")
        if exp.get("skills_highlighted"):
            print(f"    侧重的技能: {exp.get('skills_highlighted')}")

    print()
    return result


def compare_results(result_a, result_b, label_a, label_b):
    print("\n" + "=" * 60)
    print("📊 质量对比分析")
    print("=" * 60)

    if result_a is None or result_b is None:
        print("❌ 无法完整对比，请检查错误")
        return

    tr_a = result_a.get("tailored_resume", {})
    tr_b = result_b.get("tailored_resume", {})

    # 技能对比
    skills_a = set(tr_a.get("skills", []))
    skills_b = set(tr_b.get("skills", []))
    common_skills = skills_a & skills_b
    only_a = skills_a - skills_b
    only_b = skills_b - skills_a

    print(f"\n🔹 技能对比:")
    print(f"   {label_a} 独有 ({len(only_a)}): {', '.join(only_a) if only_a else '(无)'}")
    print(f"   {label_b} 独有 ({len(only_b)}): {', '.join(only_b) if only_b else '(无)'}")
    print(f"   共同 ({len(common_skills)}): {', '.join(common_skills) if common_skills else '(无)'}")

    if len(only_a) > 0 and len(only_b) > 0:
        print(f"   ✅ 技能差异化明显 — 系统正确根据 JD 筛选了不同技能")
    else:
        print(f"   ⚠️ 技能差异不足 — 可能未充分定制")

    # 工作经历改写对比
    print(f"\n🔹 工作经历改写对比:")
    exps_a = tr_a.get("experiences", [])
    exps_b = tr_b.get("experiences", [])

    for i in range(max(len(exps_a), len(exps_b))):
        exp_a = exps_a[i] if i < len(exps_a) else None
        exp_b = exps_b[i] if i < len(exps_b) else None
        if exp_a and exp_b:
            title = exp_a.get("title") or exp_b.get("title")
            company = exp_a.get("company") or exp_b.get("company")
            print(f"\n   📍 {title} @ {company}")

            bullets_a = [b.get("text", "")[:80] for b in exp_a.get("bullets", [])]
            bullets_b = [b.get("text", "")[:80] for b in exp_b.get("bullets", [])]

            # 检查 bullet 是否不同
            if bullets_a and bullets_b:
                all_same = all(a == b for a, b in zip(bullets_a, bullets_b))
                if not all_same:
                    print(f"      ✅ Bullet 内容已按 JD 分别改写")
                else:
                    print(f"      ⚠️ Bullet 内容完全相同 — 可能未定制")
                print(f"      [{label_a}] {bullets_a[0]}")
                print(f"      [{label_b}] {bullets_b[0]}")

    # 定制摘要对比
    summary_a = (tr_a.get("tailoring_summary") or "")[:200]
    summary_b = (tr_b.get("tailoring_summary") or "")[:200]
    print(f"\n🔹 定制摘要:")
    print(f"   [{label_a}] {summary_a}")
    print(f"   [{label_b}] {summary_b}")

    # 综合评定
    print(f"\n" + "-" * 60)
    passed = (len(only_a) > 0 and len(only_b) > 0)
    print(f"{'✅ 结论: 系统能根据不同 JD 生成差异化定制简历' if passed else '⚠️ 结论: 差异化不足，需检查定制 Prompt 或 LLM'}")
    print("-" * 60)


# =============================================================================
# 执行
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("📋 简历定制质量检测")
    print("   JD1: 量化风险分析师 (强相关)")
    print("   JD2: 数据平台/MLOps 工程师 (差异大)")
    print("=" * 60)

    test_upload_resume()

    result_risk = test_tailor("量化风险分析师", JD_RISK)
    result_mlops = test_tailor("MLOps工程师", JD_MLOPS)

    if result_risk and result_mlops:
        compare_results(result_risk, result_mlops, "量化风险分析师", "MLOps工程师")
    else:
        print("\n❌ 测试未完成，请检查后端运行状态和 API Key 配置")
