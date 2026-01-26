[joe@jomcgi.dev](mailto:joe@jomcgi.dev) | [linkedin/jomcgi](https://www.linkedin.com/in/jomcgi/) | [github/jomcgi](https://github.com/jomcgi) | Vancouver

## Joe McGinley

As a Senior Platform Engineer, I build and operate reliable, cost-effective distributed systems, primarily using GCP and Kubernetes. I thrive on improving performance and stability, having drastically cut processing times (weeks down to minutes), reduced costs by up to 89%, and eliminated recurring SLA violations. My approach relies on pragmatic automation, leveraging OpenTelemetry for deep system insights, and robust system design, especially for critical data platforms.

### Work Experience

#### BenchSci - Senior Software Engineer II (Promoted Oct 2023) | Oct 2022 – Present

- Stabilized a critical, frequently failing product, **reducing incident Time-to-Resolve (TTR) by 40% and eliminating recurring SLA violations**, by leading a cross-functional Root Cause Analysis (RCA) squad to produce an RCA playbook and a backlog of automated tests and reliability improvements for service owners.
- Reduced core document processing time from **weeks to minutes** by designing and building a scalable (25m+ docs) distributed event processing framework (Kubernetes/GKE), engineered for high resilience, scaling to cloud quota limits, and **scaling to zero for cost efficiency** enabling an 89% reduction in processing costs.
- Optimized transactional write throughput for our primary 10TB Postgres database utilizing PGvector (HNSW), enabling significantly faster ingestion of customer data while balancing high-performance reads under strict infrastructure scaling constraints.
- Managed and performance-tuned a large-scale Neo4j knowledge graph, optimizing complex query performance and data ingestion pipelines for essential company insights.
- Reduced incident Time-to-Identify (TTI) from **94 to 23 minutes and cut false alerts by 15%** by driving company-wide OpenTelemetry adoption, creating a unified observability standard (logs, metrics, traces) and centralizing monitoring/alerting.
- Implemented an SLO framework translating business needs into measurable reliability targets, **designed for low-friction developer adoption**, guiding data-informed prioritization and clearly communicating essential non-functional requirements.
- Increased data release stability from bi-weekly failures to >30 days uptime using automated recovery and OpenTelemetry, **allowing developers to ship features faster with reduced risk to users**.
- Cut critical Postgres processing time by **55%** (to 9 hrs) via tuning and scaling, **enabling a faster release cadence and improving core software delivery performance metrics**.
- Served as the go-to expert for data orchestration, resolving complex cross-team workflow challenges and ensuring successful platform adoption.

#### Ensono - Platform Engineering Consultant - May 2022 to Oct 2022

- Architected and delivered a greenfield data platform on Google Cloud (GCP) for a major hotel chain, enabling self-service analytics for diverse stakeholders from HQ to individual hotel GMs.
- Engineered data ingestion and processing pipelines using Cloud Composer (Airflow), integrating robust data quality checks to ensure data integrity and reliability.
- Improved platform resilience and data availability through targeted architectural enhancements and operational best practices, supporting critical business decision-making.

#### Hometree - Senior Platform Engineer - Sep 2021 to May 2022

- Optimized production database ER models to improve data access efficiency and simplify application development integration.
- Enhanced the resilience and operational reliability of a legacy data platform through targeted improvements and implementing engineering best practices.
- Modernized data modeling and transformation using DBT/BigQuery, increasing data consistency and visibility across the business.
- Provided data engineering guidance to Full Stack teams, enhancing data handling within core applications.

#### AXA - Senior Platform Engineer - Jan 2021 to Sep 2021

- Designed robust batch and streaming ETL architectures enabling scalable data processing on Azure.
- Implemented automated infrastructure provisioning (Terraform) and deployment pipelines (CI/CD with Azure DevOps), improving platform stability and deployment velocity.
- Deployed key data services and infrastructure, including systems supporting ML applications that drove significant cost savings (e.g., 40% CAC reduction).
- Consulted cross-functionally on data platform projects, influencing technical direction and implementation standards.

#### Sky - Platform Engineer - Feb 2020 to Jan 2021

- Executed the migration of a core on-premise data platform to GCP, improving system scalability and unlocking new data exploration avenues.
- Designed and maintained robust, fault-tolerant ETL processes, increasing the resilience and reliability of critical data pipelines.
- Advanced team technical skills by mentoring engineers and analysts on development standards and new technologies.

### Personal projects

- Actively contributing code and performing peer reviews for the OpenTelemetry project ([opentelemetry-python](https://github.com/open-telemetry/opentelemetry-python), [opentelemetry-python-contrib](https://github.com/open-telemetry/opentelemetry-python-contrib)).
- Designed and operate a bare-metal Kubernetes cluster (K3s) as a practical environment for reliability engineering experimentation.
- Centralized observability using the **OpenTelemetry Collector** to process diverse signals (traces, metrics, logs from cluster/apps, GitHub webhook -> Otel traces); data forwarded to **Grafana Cloud and Honeycomb** for analysis, alerting, and SLO tracking.
- Automated infrastructure and deployments using **GitOps CI/CD principles**, ensuring high availability awareness through **layered monitoring**: **Uptime Kuma** for on-site checks/alerts, backed by a **GCP uptime check with SMS alerting** monitoring the primary monitoring service itself.

### Technical Expertise

**Cloud & Infrastructure:** Google Cloud Platform (GCP), Azure, Kubernetes (GKE), Terraform, Infrastructure-as-Code (IaC)

**Reliability Engineering:** SLO Definition & Implementation, Incident Management & Post-mortems, Monitoring & Alerting, Chaos Engineering

**Observability:** OpenTelemetry (OTel), Prometheus, Grafana, Distributed Tracing, Structured Logging

**Development:** Go, Python, Event-Driven Architecture, Microservices, API Design (REST)

**Databases & Data Systems:** Postgres (incl. PGvector tuning), Neo4j, BigQuery, Data Modeling, Database Optimization, Cloud Pub/Sub, ETL/Data Pipeline Design, Data Orchestration (Airflow/Composer)
