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

### Architecture

See [DESIGN.md](./DESIGN.md) for detailed architecture documentation.

**Modern Cloudflare Routes API approach:**
- Uses Published Application Routes API (not ConfigMaps)
- Automatic DNS record creation via Routes API
- Zero Trust integration with Access Policies and Applications
- Secure by default (Zero Trust enabled unless disabled)

### Implementation Status

#### Completed Features
* [x] CloudflareTunnel CRD and controller - Manages tunnel lifecycle
* [x] Token-based tunnel authentication - Modern approach using tunnel tokens
* [x] Daemon mode - Auto-creates default shared tunnel on startup
* [x] OpenTelemetry tracing - Full observability integration

#### In Progress (See DESIGN.md)
* [ ] **CloudflareAccessPolicy CRD** - Reusable Zero Trust policies (create or reference existing)
* [ ] **CloudflareAccessApplication CRD** - Zero Trust applications per hostname
* [ ] **CloudflarePublishedRoute CRD** - Published routes (creates DNS + routing automatically)
* [ ] **Service annotation controller** - Watch Services and auto-create routes from annotations

#### Planned Features
* [ ] Kubernetes Ingress support - Standard Ingress controller implementation
* [ ] Multi-tunnel support - Multiple tunnels per cluster
* [ ] Advanced routing - Path-based routing, weighted routes
* [ ] Validation webhooks - Admission webhooks for CRD validation

### Migration Notes

**Old approach (deprecated):**
- `UpdateTunnelConfiguration()` API with ConfigMap-based routing
- Manual DNS record management

**New approach (current):**
- Published Application Routes API (DNS created automatically)
- Zero Trust integration built-in
- Annotation-driven workflow

See [DESIGN.md](./DESIGN.md) for complete migration guide.

