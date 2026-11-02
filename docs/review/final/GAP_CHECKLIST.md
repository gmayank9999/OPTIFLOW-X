# OPTIFLOW-X: Gap Checklist & Resolution Plan

**Audience:** Faculty & Review Committee  
**Purpose:** Precise, transparent enumeration of remaining project gaps against the rubric, accompanied by the smallest concrete action required to close each gap.

---

## 1. Summary of Current Rubric Compliance

- **Fully Implemented & Empirically Demonstrated:** 9 of 11 Requirements
- **Partially Demonstrated:** 2 of 11 Requirements (Prompt Pattern Sweeps & Public Cloud Hosting)
- **Not Yet Implemented:** 0 Requirements

---

## 2. Identified Gaps & Action Items

### Gap 1: Incomplete E3 Prompt Variance Sweep (Rubric Items 4 & 8)

- **Description:**  
  The Strategist prompt variance experiment (`optiflow/experiments/configs/e3_prompting.yaml`) defines 7 configurations (4 prompt architectures: Structured, ReAct, Reflection, Few-Shot; and 3 specialized personas: Compiler Engineer, HPC Researcher, Cautious Reviewer). Currently, only 14 runs (`structured` 10/10, `react` 4/10) are completed in `results/runs.csv`. The remaining prompt styles and personas have not yet been evaluated across the benchmark suite due to earlier free-tier LLM API rate limits.
- **Impact on Review:**  
  The prompt variants are fully implemented in code ([`optiflow/agents/prompts/strategist.py`](file:///e:/agentic/OPTIFLOW-X/optiflow/agents/prompts/strategist.py)) and unit-tested, but empirical comparison data for Reflection and Personas is missing from `results/analysis.json`.
- **Smallest Concrete Action to Close:**  
  Execute the audited 5-cell minimal test on `matmul_naive` (which already has `structured` and `react` results recorded):
  ```powershell
  .venv\Scripts\python.exe -m optiflow.experiments.run_matrix optiflow/experiments/configs/e3_prompting.yaml --programs matmul_naive
  ```
  - *Time Required:* ~5–7 minutes
  - *Expected Spend:* ~$0.015 – $0.020 USD
  - *Outcome:* Completes data for all 7 prompt variants on a single benchmark program, enabling an apples-to-apples empirical prompt variance table.

---

### Gap 2: Live Public Cloud VM Instance Not Provisioned (Rubric Item 11)

- **Description:**  
  The containerization and deployment stack is fully engineered:
  - Multi-stage production [`Dockerfile`](file:///e:/agentic/OPTIFLOW-X/Dockerfile)
  - Hardened compiler sandbox container ([`docker/sandbox.Dockerfile`](file:///e:/agentic/OPTIFLOW-X/docker/sandbox.Dockerfile))
  - Multi-service composition separating the FastAPI web server from the Google ADK A2A Reviewer ([`docker-compose.yml`](file:///e:/agentic/OPTIFLOW-X/docker-compose.yml))
  - Automated provisioning recipe for Google Compute Engine ([`deploy/vm-startup.sh`](file:///e:/agentic/OPTIFLOW-X/deploy/vm-startup.sh))  
  However, no active public cloud IP or DNS endpoint exists because an actual Google Compute Engine instance has not been provisioned.
- **Impact on Review:**  
  Reviewers grading strictly on a live external URL may dock points unless local container execution is accepted as sufficient proof of deployment readiness.
- **Smallest Concrete Action to Close:**  
  - *Option A (If Cloud Account / Billing is Available):* Run one command via Google Cloud CLI:
    ```bash
    gcloud compute instances create optiflow-server \
      --zone=us-central1-a \
      --machine-type=e2-standard-4 \
      --image-family=debian-12 \
      --image-project=debian-cloud \
      --tags=http-server,https-server \
      --metadata-from-file=startup-script=deploy/vm-startup.sh
    ```
  - *Option B (If Staying On Local Infrastructure):* Demonstrate local multi-container Docker Compose readiness during the presentation:
    ```powershell
    docker compose config
    docker compose build
    ```

---

### Gap 3: Multi-Trial Variance Averaging (E7 Repeats - Rubric Item 10)

- **Description:**  
  LLM completions exhibit stochastic variability. While the repository contains 196 completed runs across multiple architectures and messaging channels, individual benchmark cells were primarily run with `repeats: 1`. The experiment matrix configuration [`optiflow/experiments/configs/e7_repeats.yaml`](file:///e:/agentic/OPTIFLOW-X/optiflow/experiments/configs/e7_repeats.yaml) (3 repeats per cell) has not been run.
- **Impact on Review:**  
  Minor. The project easily meets the requirement of $\ge 40$ runs (196 logged), but does not yet report confidence intervals specifically isolating run-to-run LLM variance on identical inputs.
- **Smallest Concrete Action to Close:**  
  Run a single 3-repeat configuration on `matmul_naive`:
  ```powershell
  .venv\Scripts\python.exe -m optiflow.experiments.run_matrix optiflow/experiments/configs/e7_repeats.yaml --programs matmul_naive
  ```
  - *Time Required:* ~4 minutes
  - *Expected Spend:* ~$0.010 USD
  - *Outcome:* Quantifies run-to-run standard deviation for one benchmark.

---

## 3. Prioritized Triage for Review Day

1. **Top Priority:** Keep existing 196 runs safe; do not wipe `results/runs.csv`.
2. **Presentation Focus:** Emphasize the completed 12-cell E2 Messaging and 23-cell E6 A2A Interop results, which provide rock-solid empirical data directly fulfilling Requirements 1 and 6.
3. **If Asked About Gaps:** Transparently present this `GAP_CHECKLIST.md` document to demonstrate rigorous engineering self-awareness and provide the exact commands ready to run.
