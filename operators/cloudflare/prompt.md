## Project Prompt: Cloudflare Zero Trust Kubernetes Operator Integration

**1. Core Value Proposition:**
* **Problem:** Managing Cloudflare tunnels and Zero Trust policies requires coordination across multiple operators and manual steps, creating friction and cognitive load when exposing services in Kubernetes.
* **Solution:** Extend existing operators with shared annotations and coordination logic to automatically create Zero Trust applications that integrate seamlessly with tunnel deployment.
* **Value:** Eliminates manual coordination steps and prevents security gaps by ensuring Zero Trust policies are applied before tunnel exposure.

**2. Intended Use Case:**
* **Primary User:** Homelab operator (yourself) managing personal services with Cloudflare Zero Trust protection.
* **Scenario:** Developer annotates a Kubernetes service with hostname and Zero Trust policy requirements. The operator automatically creates the Zero Trust application and coordinates with tunnel operators to ensure secure exposure only after policies are in place.

**3. MVP Scope & Key Features:**
* Annotation-driven Zero Trust application creation (`cloudflare.io/access-enabled`, `cloudflare.io/access-policy`)
* Shared hostname annotation for operator coordination (`cloudflare.io/hostname`)
* ConfigMap-based policy template system (map policy names like "personal-access" to email lists)
* Integration hooks to prevent tunnel exposure without Zero Trust configuration
* **Explicitly de-scoped for MVP:** Tunnel management (handled by adyanth operator), DNS record management, complex policy rules beyond basic email/group access

**4. Technical Constraints & Considerations:**
* **Stack:** Kubernetes operator using controller-runtime, integrating with existing adyanth/cloudflare-operator
* **Key Design Principle:** Security-first coordination - never expose ingress without proper Zero Trust application configured

**5. Acceptance Criteria & Testing Plan:**
* **Behavior 1:** User annotates service with Zero Trust requirements
  * **Test:** Verify Zero Trust application is created in Cloudflare with correct hostname and policy
* **Behavior 2:** User annotates service with invalid policy name  
  * **Test:** Verify operator reports error and does not create application
* **Behavior 3:** Service has Zero Trust annotations but tunnel operator tries to expose it
  * **Test:** Verify tunnel exposure is blocked until Zero Trust application exists
* **Behavior 4:** Policy ConfigMap is updated
  * **Test:** Verify existing Zero Trust applications are updated with new policy rules

**6. Post-MVP & Future Extensions:**
* **Unified Operator Evolution:** Gradually absorb tunnel and DNS management capabilities to create the comprehensive unified operator described in the architecture analysis
* **Advanced Policy Features:** Support for complex access rules (IP-based, device trust, session controls), SAML/OIDC integration, conditional access based on risk scores
* **Multi-tenant Support:** Policy inheritance, namespace-based policy scoping, tenant isolation for platform team use cases
* **Gateway Integration:** Network-level policies, WARP device enrollment, browser isolation configuration
* **Monitoring & Observability:** Access log aggregation, policy violation alerts, compliance reporting dashboards
* **GitOps Integration:** Policy-as-code workflows, automated policy validation, drift detection

**7. Call to Action: Implementation Strategy**
* **Your Task:** Implement the Zero Trust operator integration described in this brief.
* **Process:**
  1. **Plan First:** Propose a high-level technical plan including operator architecture, CRD design, and integration points with existing operators.
  2. **Await Approval:** Present the plan for review and feedback.
  3. **Execute Step-by-Step:** Begin implementing, starting with the Zero Trust controller and policy system.