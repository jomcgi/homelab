# cloudflare

Manage cluster ingress via annotations using cloudflare tunnels.

## Desired state (WIP)

This operator is a work in progress.

#### Example annotations

```
metadata:
  annotations:
    cloudflare.ingress.hostname: test-ingress.jomcgi.dev
    cloudflare.zero-trust.policy: joe-only
```

#### Control flow

```mermaid
flowchart TB
    %% Main Components
    Deploy[Kubernetes Deployment<br/>with Annotations]
    Controller[Cloudflare Operator<br/>Controller Daemon]

    %% CRDs and State
    DNSRecord[DNS Record CRD]
    ZTApp[Zero Trust App CRD]
    Policy[Access Policy CRD]
    Ingress[Ingress CRD]
    ConfigMap[ConfigMap<br/>Routing Rules]
    Tunnel[Cloudflared Tunnel<br/>Deployment]

    %% External State
    CFState[(Cloudflare State<br/>DNS/ZT/Policies)]

    %% Control Loop Start - Monitoring
    Deploy -.->|"Watch events<br/>(annotations changed)"| Controller
    DNSRecord -.->|"Watch CRD status"| Controller
    ZTApp -.->|"Watch CRD status"| Controller
    Policy -.->|"Watch CRD status"| Controller
    Ingress -.->|"Watch CRD status"| Controller
    CFState -.->|"Verify external state<br/>(API polling delay)"| Controller

    %% Decision Point
    Controller --> Decision{Reconcile?<br/>Desired ≠ Actual}

    %% No Action Path
    Decision -->|"States match<br/>(stable)"| Wait[Wait for next event]
    Wait -.->|"Requeue 30-60s"| Controller

    %% Control Actions - Ordered Sequence
    Decision -->|"Drift detected"| Step1[1. Create/Update<br/>DNS Record CRD]
    Step1 ==> DNSRecord
    DNSRecord ==> |"Sync to Cloudflare"| CFState

    DNSRecord --> Step2[2. Create/Update<br/>Zero Trust App CRD]
    Step2 ==> ZTApp
    ZTApp ==> |"Sync to Cloudflare"| CFState

    ZTApp --> Step3{3. Find Policy<br/>joe-only exists?}
    Step3 -->|"Yes"| Step4[4. Apply Policy<br/>to ZT App]
    Step3 -->|"No"| Error[Create Policy CRD<br/>or Error]

    Step4 ==> Policy
    Policy ==> |"Link in Cloudflare"| CFState

    Policy --> Step5[5. Create Ingress<br/>for Deployment]
    Step5 ==> Ingress

    Ingress --> Step6[6. Update ConfigMap<br/>with routing]
    Step6 ==> ConfigMap

    ConfigMap -.->|"Mounted by"| Tunnel
    Tunnel -.->|"Routes traffic using"| CFState

    %% Finalizer Cleanup Loop
    Deploy -.->|"Deletion event"| Finalizer{Finalizers<br/>present?}
    Finalizer -->|"Yes"| Cleanup[Cleanup External State<br/>in order]
    Cleanup ==> DeleteCF[Delete from Cloudflare]
    DeleteCF ==> DeleteCRDs[Delete CRDs]
    DeleteCRDs --> RemoveFinalizer[Remove Finalizers]
    RemoveFinalizer -.->|"Allow deletion"| Deploy

    Finalizer -->|"No"| Deploy

    %% Feedback consolidation
    CFState -.->|"State feedback<br/>(DNS propagation delay 2-5min)"| Controller

    %% Styling
    classDef monitor fill:#e1f5ff,stroke:#0066cc,stroke-width:2px
    classDef decision fill:#fff4e1,stroke:#ff9900,stroke-width:2px
    classDef action fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px
    classDef external fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px
    classDef feedback fill:#fff3e0,stroke:#ef6c00,stroke-width:2px,stroke-dasharray: 5 5

    class Controller,Wait monitor
    class Decision,Finalizer,Step3 decision
    class Step1,Step2,Step4,Step5,Step6,Cleanup,DeleteCF,DeleteCRDs,RemoveFinalizer action
    class CFState,Tunnel external

    %% Notes
    Note1[/"⚙️ STABILIZING LOOP: Controller corrects drift<br/>⏱️ DELAYS: CF API calls, DNS propagation 2-5min<br/>🔒 FINALIZERS: Prevent orphaned external resources"/]
    style Note1 fill:#fff9c4,stroke:#f57f17,stroke-width:2px
```

### TODO

#### Missing Features

- Deployment/Service annotation watching - No automatic tunnel creation from app annotations
- DNS Record CRD and controller - No automated DNS management
- Zero Trust Application CRD and controller - No automated Access app creation
- Access Policy CRD and controller - No policy management
- ConfigMap-based tunnel routing - Currently uses Cloudflare API config only
- Kubernetes Ingress support - No standard Ingress controller implementation
- Prometheus metrics export - No observability metrics
- Multiple tunnel support per app - One-to-one mapping only

#### Tasks to complete

Keep these tasks small, iterative and isolated.
They should be listed in the order that they should be implemented.

##### Shared Tunnel Infrastructure

1. [x] **Ensure shared tunnel creation on startup** - Operator creates one CloudflareTunnel CRD if not exists (implemented with `--enable-daemon`)
2. [ ] **Switch to ConfigMap-based routing** - Update CloudflareTunnel controller to generate ConfigMap from ingress rules
3. [ ] **Update cloudflared daemon config** - Mount ConfigMap, use `--config` flag instead of Cloudflare API config

##### Deployment Annotation Watching

4. [ ] **Create Deployment annotation controller scaffold** - Watch Deployments with `cloudflare.ingress.hostname`
5. [ ] **Add RBAC for Deployment watching** - Grant `apps/deployments [get;list;watch]` and `core/services [get;list]` permissions
6. [ ] **Implement Service discovery** - Find Service for Deployment by label selector, build `http://svc:port` URL

##### DNS Management

7. [ ] **Create DNS Record CRD** - Define API types for DNS record management (hostname, target, proxied)
8. [ ] **Add DNS Record controller** - Create CNAME records pointing to tunnel endpoint when DNSRecord CRD created
9. [ ] **Integration: Deployment → DNS Record** - Deployment controller creates DNSRecord CRD from annotation

##### Zero Trust Integration

10. [ ] **Create Zero Trust Application CRD** - Define API types for Access applications
11. [ ] **Add Zero Trust Application controller** - Create Access apps in Cloudflare when ZTApp CRD created
12. [ ] **Create Access Policy CRD** - Define API types for Access policies (email, IP, geo rules)
13. [ ] **Add Access Policy controller** - Link policies to applications in Cloudflare
14. [ ] **Integration: Deployment → ZT App** - Deployment controller creates ZTApp CRD from `cloudflare.zero-trust.policy` annotation

##### ConfigMap Routing Updates

15. [ ] **Update ConfigMap on DNS Record creation** - Add ingress rule to shared tunnel's ConfigMap when DNSRecord created
16. [ ] **Add finalizers for cleanup** - Remove ConfigMap entries when DNSRecord deleted

##### Observability & Testing

17. [ ] **Add Prometheus metrics** - Export controller metrics on `:8080/metrics`
18. [ ] **Add integration tests** - Test complete annotation → DNS → ZT → ConfigMap → tunnel flow
19. [ ] **Add Ingress controller** - Watch standard Kubernetes Ingress resources (future)
