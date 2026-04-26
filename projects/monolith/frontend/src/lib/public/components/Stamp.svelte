<!-- Fixed "h." signature mark in bottom-left corner -->
<div class="stamp" aria-hidden="true">h<span class="stamp-dot">.</span></div>

<style>
  .stamp {
    position: fixed;
    bottom: 18px;
    left: 18px;
    z-index: 40;
    width: 44px;
    height: 44px;
    border-radius: 999px;
    background: var(--ink);
    color: var(--cream);
    display: flex;
    align-items: center;
    justify-content: center;
    font-family: var(--serif);
    font-size: 22px;
    border: 1.5px solid var(--ink);
    box-shadow: 3px 3px 0 var(--accent);
    pointer-events: none;
  }

  .stamp::after {
    content: "";
    position: absolute;
    inset: 4px;
    border-radius: 999px;
    border: 1px dashed rgba(255, 255, 255, 0.3);
    animation: spin-slow 22s linear infinite;
  }

  .stamp-dot {
    color: var(--accent);
  }

  @keyframes spin-slow {
    to {
      transform: rotate(360deg);
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .stamp::after {
      animation: none;
    }
  }
</style>
