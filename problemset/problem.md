### At a Glance

| Section | Detail |
| --- | --- |
| **Core Goal** | Build a working fuel operations decision-support platform on top of the organizer-provided simulator.

 |
| **Must Include** | Operator-facing application, backend, intelligence component, deployment, observability, resilience, and load testing.

 |
| **Intelligence** | At least one meaningful AI/ML/optimization/detection capability. Reinforcement learning is optional.

 |
| **Environment** | All teams integrate with the same BUP Fuel Supply Simulator.

 |
| **Hackathon Dynamic** | Organizers may introduce surprise domain and engineering events during development or judging.

 |
| **Deployment** | The system must be reproducibly runnable, preferably containerized.

 |
| **Judging Focus** | Working product, decision usefulness, architecture, DevOps, resilience, observability, and live demonstration.

 |

---

### 1. Executive Summary

Bangladesh's simulated fuel supply network consists of interconnected supply points, depots, transportation routes, regions, fuel stations, and customer demand. A disruption at one stage can affect the rest of the network. A delayed shipment may reduce depot inventory. A demand spike can create regional shortages. A route failure can make an otherwise valid allocation impossible.

Your challenge is to build an intelligent Fuel Supply Operations Platform capable of:

* Observing the current simulated fuel network;


* Identifying emerging shortages and operational risks;


* Helping operators decide how constrained fuel should be allocated;


* Responding to unexpected disruptions;


* Exposing the reasoning behind important recommendations;


* Remaining observable and usable during application or service failures;


* Demonstrating measurable system performance under load.



The platform must operate entirely against the BUP Fuel Supply Simulator provided by the organizers. No real fuel infrastructure will be accessed or controlled.

---

### 2. Primary Engineering Challenge

#### Primary Engineering Question

Can your team build, deploy, and operate an intelligent system that helps a fuel operations center respond to changing demand, constrained supply, operational disruptions, and software failures?

Your solution should demonstrate the complete engineering loop:


$$\text{Observe} \rightarrow \text{Detect} \rightarrow \text{Predict} \rightarrow \text{Decide} \rightarrow \text{Simulate} \rightarrow \text{Act} \rightarrow \text{Monitor} \rightarrow \text{Recover}$$

The emphasis is not on achieving the highest ML accuracy alone. Judges should be able to interact with and observe a working system.

---

### 3. Scenario

The system represents a simulated fuel supply chain:

$$\text{Import / Supply} \rightarrow \text{Port / Arrival} \rightarrow \text{Depot / Storage} \rightarrow \text{Distribution / Transport} \rightarrow \text{Fuel Stations} \rightarrow \text{Customer Demand}$$

The primary fuel categories are Diesel, Petrol, and Octane. Teams may model additional operational concepts when useful.

---

### 4. Organizer-Provided Fuel Supply Simulator

All teams will receive access to the same BUP Fuel Supply Simulator. The simulator acts as the simulated operational environment for the hackathon.

It will provide information such as:

* Depots and stations;


* Inventory by fuel type;


* Regional demand;


* Incoming supply;


* Transport routes and travel constraints;


* Supply delays;


* Operational events and crisis conditions.



Teams will interact with the simulator through documented APIs. Example conceptual endpoints may include:

* `GET /stations`

* `GET /depots`

* `GET /supply-arrivals`

* `GET /demand-history`

* `GET /routes`

* `GET /events`

* `POST /allocations`


> **Important**: Teams are not required to build their own fuel-supply simulator. The organizers provide the operational world. Your job is to build the intelligent system that operates on top of it.
> 
> 

---

### 5. What Your Team Must Build

Each team must build a complete end-to-end platform for fuel supply intelligence and resilience. The system should handle data collection and management, perform analysis, support decision-making, provide applications and operator tools, and include monitoring capabilities.

---

### 6. Application Requirement

Every team must build a usable operator-facing application. A notebook alone is not considered a complete submission.

The application should allow an operator to understand the current state of the fuel network and interact with the team's decision-support system. The application should include a meaningful subset of:

* Current fuel inventory;


* Depot and station status;


* Regional fuel demand;


* Shortage alerts;


* Projected shortage risk;


* Incoming supply;


* Disruptions;


* Recommended allocations;


* Expected impact of decisions;


* System alerts;


* Decision history;


* Service health.



Teams are free to design the experience. A web application is recommended, but other interfaces may be accepted if they meaningfully support the operations workflow.

---

### 7. Intelligence Requirement

Every team must implement at least one meaningful intelligent capability. Teams may choose the techniques that best fit their architecture.

* **Prediction**: Demand forecasting, shortage prediction, stockout probability, estimated supply arrival, transport delay prediction.


* **Detection**: Anomalous demand, abnormal inventory changes, supply-chain bottlenecks, emerging regional disruptions.


* **Decision Intelligence**: Constrained optimization, heuristic allocation, priority-based allocation, reinforcement learning, mathematical optimization, hybrid policies.


* **Generative AI**: Incident explanation, supply-chain state summarization, operator investigation assistance, human-readable decision explanations.



LLMs should support the operational system rather than merely provide a chatbot around the application.

---

### 8. Reinforcement Learning (Optional)

Reinforcement learning is optional. Teams that believe RL is appropriate may use it for allocation or sequential decision-making.

A possible RL formulation could include:

* **State**: Inventory, demand, predicted shortage, available supply, route availability.


* **Action**: Allocate quantity, select destination, select route, delay allocation.


* **Reward**: Reduce unmet demand, reduce transport cost, reduce stockouts, maintain service level.



If RL is used, teams should demonstrate why it provides useful behavior compared with a reasonable rule-based or heuristic approach.

---

### 9. Decision Support

Important recommendations should be inspectable. For example:

```text
ALERT
Station: DHAKA-021
Fuel: Diesel
Projected Stockout: 6.2 hours
Current Inventory: 8,400 L
Expected Demand: 11,900 L
Recommended Allocation: 5,000 L from DEPOT-03
Expected Result: Stockout risk reduced 72% → 19%
```[cite: 1]

Where appropriate, teams should show why an area is considered at risk, which signals influenced the recommendation, relevant constraints, expected impact, confidence or uncertainty, and alternative actions[cite: 1]. Human operators should remain able to inspect important decisions[cite: 1].

---

### 10. Crisis and Event Handling

During the hackathon, organizers may introduce changes to the simulated environment[cite: 1]. Examples include:

| Scenario | Example Condition | What Your System Should Show |
| :--- | :--- | :--- |
| **Shipment delay** | Incoming fuel arrives later than expected. | Warning, shortage impact, decision response, recovery.[cite: 1] |
| **Demand spike** | One or more regions experience elevated demand. | Risk change, forecast/detection response, allocation adaptation.[cite: 1] |
| **Depot constraint** | Available inventory or capacity is reduced. | Constraint handling, reallocation, service impact.[cite: 1] |
| **Regional disruption** | A route or region becomes temporarily unavailable. | Alternative allocation and recovery behavior.[cite: 1] |
| **Combined crisis** | Two or more disruptions occur together. | End-to-end resilience and failure boundaries.[cite: 1] |

Teams should demonstrate how their system detects, evaluates, responds, explains, and monitors recovery[cite: 1].

---

### 11. Application Resilience

Teams must define what happens when something goes wrong[cite: 1].

| Failure Condition | Expected Behavior |
| :--- | :--- |
| **ML model unavailable** | Fallback allocation policy[cite: 1] |
| **Invalid simulator response** | Reject input + raise alert[cite: 1] |
| **Prediction confidence too low** | Human review requested[cite: 1] |
| **Backend dependency unavailable** | Retry / cached state / degraded mode[cite: 1] |

Teams are encouraged to implement appropriate mechanisms such as fallback logic, graceful degradation, retries, timeout handling, health checks, cached state, validation, circuit breakers, and rollback[cite: 1]. Sophisticated fault-tolerance infrastructure is not mandatory; clear and demonstrable behavior is more important[cite: 1].

---

### 12. DevOps Requirement

Every system must be deployable[cite: 1]. At minimum, teams should provide a reproducible way to launch the application, for example[cite: 1]:
```bash
docker compose up
```[cite: 1]
or an equivalent documented deployment process[cite: 1].

Teams should demonstrate a basic software delivery workflow:

$$\text{Source Code} \rightarrow \text{Build} \rightarrow \text{Test} \rightarrow \text{Package} \rightarrow \text{Deploy} \rightarrow \text{Health Check} \rightarrow \text{Running Application}$$
[cite: 1]

A CI/CD workflow is strongly encouraged[cite: 1]. Examples include GitHub Actions, GitLab CI, Jenkins, or equivalent automation[cite: 1].

---

### 13. Advanced DevOps Opportunities

Teams seeking additional technical depth may implement:
* Kubernetes[cite: 1];
* Helm[cite: 1];
* Infrastructure as Code[cite: 1];
* Terraform[cite: 1];
* GitOps[cite: 1];
* Automated rollback[cite: 1];
* Blue/green deployment[cite: 1];
* Canary deployment[cite: 1];
* Autoscaling[cite: 1];
* Distributed services[cite: 1];
* Service discovery[cite: 1];
* Queue-based processing[cite: 1].

These are optional[cite: 1]. Do not introduce infrastructure complexity unless it improves your solution[cite: 1].

---

### 14. Observability Requirement

Your team must be able to understand what the system is doing[cite: 1]. Teams must implement meaningful observability covering the application[cite: 1].

| Layer | Examples |
| :--- | :--- |
| **Application** | Request rate, latency, error rate, service availability[cite: 1] |
| **System** | CPU, memory, resource utilization[cite: 1] |
| **Intelligence** | Prediction error, model confidence, shortage-alert rate, decision frequency, fallback activation[cite: 1] |
| **Logs** | Important actions, integration failures, decision events, recoveries[cite: 1] |

Distributed tracing is optional[cite: 1]. Suggested tools may include Prometheus, Grafana, OpenTelemetry, Loki, ELK, Jaeger, or equivalent tools[cite: 1]. Teams are free to choose their stack[cite: 1].

---

### 15. Health and Status

The application should expose the health of important components where meaningful[cite: 1]. Example:

| Component | Status |
| :--- | :--- |
| Backend API | Healthy[cite: 1] |
| Database | Healthy[cite: 1] |
| Fuel Simulator | Healthy[cite: 1] |
| Prediction Service | Healthy[cite: 1] |
| Decision Engine | Healthy[cite: 1] |

| Metric | Value |
| :--- | :--- |
| p95 Latency | 164 ms[cite: 1] |
| Error Rate | 0.4%[cite: 1] |

Judges should be able to understand whether the system itself is healthy[cite: 1].

---

### 16. Data

The primary operational data will come from the organizer-provided simulation environment[cite: 1].

Teams may additionally use public datasets, synthetic data, derived features, generated historical data, or additional contextual information[cite: 1]. Any external or generated data should be documented[cite: 1].

> **Focus Your Time On Building**: Teams are not required to create an entire fuel dataset from scratch[cite: 1]. The shared simulator is intended to let participants spend hackathon time building and operating solutions rather than manufacturing separate underlying worlds[cite: 1].

---

### 17. Load Testing

Each team must load-test at least one meaningful application path, such as the prediction API, decision API, simulator integration, dashboard backend, or an end-to-end decision request[cite: 1].

Teams should report relevant measurements such as:
* Average latency[cite: 1];
* p50 latency[cite: 1];
* p95 latency[cite: 1];
* p99 latency where available[cite: 1];
* Throughput[cite: 1];
* Error rate[cite: 1];
* Concurrency[cite: 1];
* Resource usage[cite: 1].

The emphasis should be on understanding the behavior and limits of the implemented system rather than achieving an arbitrary benchmark[cite: 1].

---

### 18. Security and Engineering Hygiene

Teams should demonstrate basic software engineering hygiene[cite: 1]. At minimum:
* Do not hard-code secrets[cite: 1];
* Validate external input[cite: 1];
* Handle failed requests appropriately[cite: 1];
* Document required configuration[cite: 1];
* Avoid exposing credentials[cite: 1];
* Restrict sensitive operator actions where appropriate[cite: 1].

Teams are not expected to build enterprise-grade security within the hackathon duration[cite: 1].

---

### 19. Required Deliverables

1. **Working Application**: A runnable end-to-end platform[cite: 1].
2. **Source Repository**: Application code, setup instructions, dependencies, and deployment instructions[cite: 1].
3. **Simulator Integration**: The system must interact with the official BUP Fuel Supply Simulator[cite: 1].
4. **Intelligence Component**: At least one meaningful AI, ML, optimization, detection, or decision-support capability[cite: 1].
5. **Operator Interface**: A usable interface showing meaningful operational information[cite: 1].
6. **Architecture Diagram**: A clear view of simulator data/backend intelligence decision application monitoring[cite: 1].
7. **Deployment**: A reproducible deployment method[cite: 1].
8. **Observability Evidence**: Logs, metrics, dashboards, alerts, or equivalent outputs[cite: 1].
9. **Resilience Demonstration**: Evidence showing how the application responds to at least one meaningful failure condition[cite: 1].
10. **Load-Test Evidence**: Workload definition and measured results[cite: 1].
11. **Final Demo**: A live or judge-supervised demonstration of the system[cite: 1].

---

### 20. Recommended Deliverables

* CI/CD[cite: 1];
* Automated tests[cite: 1];
* Experiment tracking[cite: 1];
* Model versioning[cite: 1];
* Decision audit history[cite: 1];
* Deployment versioning[cite: 1];
* Simulation replay[cite: 1];
* Scenario configuration[cite: 1];
* Automated fallback[cite: 1];
* Rollback[cite: 1].

---

### 21. Optional Advanced Work

* Reinforcement learning[cite: 1];
* Multi-agent decision systems[cite: 1];
* Optimization + ML hybrids[cite: 1];
* Uncertainty-aware allocation[cite: 1];
* Counterfactual simulation[cite: 1];
* Automated incident detection[cite: 1];
* Policy rollback[cite: 1];
* Drift detection[cite: 1];
* Event-driven architecture[cite: 1];
* Streaming systems[cite: 1];
* Kubernetes deployment[cite: 1];
* Autoscaling[cite: 1];
* Generative-AI operations assistants[cite: 1].

Complexity itself will not guarantee a higher score[cite: 1]. The implementation must meaningfully contribute to the solution[cite: 1].

---

### 22. Suggested Demonstration Story

1. Normal operations[cite: 1]
2. Operator dashboard[cite: 1]
3. Demand starts increasing[cite: 1]
4. System detects risk[cite: 1]
5. Intelligence layer predicts shortage[cite: 1]
6. Allocation recommendation generated[cite: 1]
7. Operator inspects recommendation[cite: 1]
8. Allocation is simulated[cite: 1]
9. Crisis event occurs[cite: 1]
10. System adapts[cite: 1]
11. Application or dependency failure is injected[cite: 1]
12. Monitoring detects failure[cite: 1]
13. Fallback/recovery activates[cite: 1]
14. Operations continue[cite: 1]

---

### 23. Evaluation Criteria

| Criterion | Weight | What Will Be Assessed |
| :--- | :---: | :--- |
| **Working Product & User Experience** | **20%** | Functional application, operational workflow, usability, completeness[cite: 1]. |
| **Intelligence & Decision Quality** | **20%** | Usefulness and quality of AI/ML/optimization/detection; appropriate methodology[cite: 1]. |
| **Architecture & Integration** | **15%** | Backend engineering, simulator integration, component design, technical coherence[cite: 1]. |
| **DevOps & Engineering Quality** | **15%** | Deployment, automation, testing, maintainability, engineering practices[cite: 1]. |
| **Resilience & Incident Response** | **10%** | Failure handling, crisis response, fallback behavior, recovery[cite: 1]. |
| **Observability & Performance** | **10%** | Monitoring, metrics, logs, health visibility, load testing[cite: 1]. |
| **Demo & Problem Understanding** | **10%** | Clear explanation, understanding of constraints, effective demonstration[cite: 1]. |
| **Total** | **100%** | |

---

### 24. Constraints and Guardrails

* Operate only against the simulation environment[cite: 1].
* Do not interact with real fuel infrastructure[cite: 1].
* Do not execute real purchases or dispatches[cite: 1].
* Do not use real credentials or private operational systems[cite: 1].
* Distinguish simulated results from real-world fuel conditions[cite: 1].
* Document important assumptions[cite: 1].
* Preserve human review for consequential simulated decisions[cite: 1].

---

### 25. Success Criteria

The strongest solutions will not necessarily contain the most complicated model[cite: 1]. Successful teams will demonstrate that they can turn intelligence into a working engineered system[cite: 1].

$$\text{Useful Application} + \text{Meaningful Intelligence} + \text{Reliable Backend} + \text{Deployment} + \text{Observability} + \text{Resilience} + \text{Measured Performance} = \mathbf{Operational\ AI\ System}$$
[cite: 1]

---

### 26. Final Challenge Statement

#### Final Challenge
Build an intelligent Fuel Supply Operations Platform that can observe a simulated fuel network, identify emerging risks, recommend or simulate operational decisions, withstand disruptions, and remain observable and usable when components fail[cite: 1].

Your team will integrate with the official BUP Fuel Supply Simulator and build the application, backend, intelligence layer, deployment workflow, and operational tooling around it[cite: 1]. During the hackathon, the environment may change[cite: 1].

**Your job is not only to build the system. Your job is to keep it working.**[cite: 1]

```