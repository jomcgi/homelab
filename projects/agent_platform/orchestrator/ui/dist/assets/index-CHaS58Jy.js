(function () {
  const u = document.createElement("link").relList;
  if (u && u.supports && u.supports("modulepreload")) return;
  for (const f of document.querySelectorAll('link[rel="modulepreload"]')) c(f);
  new MutationObserver((f) => {
    for (const s of f)
      if (s.type === "childList")
        for (const d of s.addedNodes)
          d.tagName === "LINK" && d.rel === "modulepreload" && c(d);
  }).observe(document, { childList: !0, subtree: !0 });
  function r(f) {
    const s = {};
    return (
      f.integrity && (s.integrity = f.integrity),
      f.referrerPolicy && (s.referrerPolicy = f.referrerPolicy),
      f.crossOrigin === "use-credentials"
        ? (s.credentials = "include")
        : f.crossOrigin === "anonymous"
          ? (s.credentials = "omit")
          : (s.credentials = "same-origin"),
      s
    );
  }
  function c(f) {
    if (f.ep) return;
    f.ep = !0;
    const s = r(f);
    fetch(f.href, s);
  }
})();
function Jp(i) {
  return i && i.__esModule && Object.prototype.hasOwnProperty.call(i, "default")
    ? i.default
    : i;
}
var so = { exports: {} },
  ca = {};
/**
 * @license React
 * react-jsx-runtime.production.js
 *
 * Copyright (c) Meta Platforms, Inc. and affiliates.
 *
 * This source code is licensed under the MIT license found in the
 * LICENSE file in the root directory of this source tree.
 */ var Pd;
function Fy() {
  if (Pd) return ca;
  Pd = 1;
  var i = Symbol.for("react.transitional.element"),
    u = Symbol.for("react.fragment");
  function r(c, f, s) {
    var d = null;
    if (
      (s !== void 0 && (d = "" + s),
      f.key !== void 0 && (d = "" + f.key),
      "key" in f)
    ) {
      s = {};
      for (var m in f) m !== "key" && (s[m] = f[m]);
    } else s = f;
    return (
      (f = s.ref),
      { $$typeof: i, type: c, key: d, ref: f !== void 0 ? f : null, props: s }
    );
  }
  return ((ca.Fragment = u), (ca.jsx = r), (ca.jsxs = r), ca);
}
var tp;
function Iy() {
  return (tp || ((tp = 1), (so.exports = Fy())), so.exports);
}
var R = Iy(),
  ho = { exports: {} },
  dt = {};
/**
 * @license React
 * react.production.js
 *
 * Copyright (c) Meta Platforms, Inc. and affiliates.
 *
 * This source code is licensed under the MIT license found in the
 * LICENSE file in the root directory of this source tree.
 */ var ep;
function Wy() {
  if (ep) return dt;
  ep = 1;
  var i = Symbol.for("react.transitional.element"),
    u = Symbol.for("react.portal"),
    r = Symbol.for("react.fragment"),
    c = Symbol.for("react.strict_mode"),
    f = Symbol.for("react.profiler"),
    s = Symbol.for("react.consumer"),
    d = Symbol.for("react.context"),
    m = Symbol.for("react.forward_ref"),
    y = Symbol.for("react.suspense"),
    p = Symbol.for("react.memo"),
    b = Symbol.for("react.lazy"),
    v = Symbol.for("react.activity"),
    T = Symbol.iterator;
  function x(A) {
    return A === null || typeof A != "object"
      ? null
      : ((A = (T && A[T]) || A["@@iterator"]),
        typeof A == "function" ? A : null);
  }
  var X = {
      isMounted: function () {
        return !1;
      },
      enqueueForceUpdate: function () {},
      enqueueReplaceState: function () {},
      enqueueSetState: function () {},
    },
    G = Object.assign,
    F = {};
  function Y(A, U, S) {
    ((this.props = A),
      (this.context = U),
      (this.refs = F),
      (this.updater = S || X));
  }
  ((Y.prototype.isReactComponent = {}),
    (Y.prototype.setState = function (A, U) {
      if (typeof A != "object" && typeof A != "function" && A != null)
        throw Error(
          "takes an object of state variables to update or a function which returns an object of state variables.",
        );
      this.updater.enqueueSetState(this, A, U, "setState");
    }),
    (Y.prototype.forceUpdate = function (A) {
      this.updater.enqueueForceUpdate(this, A, "forceUpdate");
    }));
  function it() {}
  it.prototype = Y.prototype;
  function K(A, U, S) {
    ((this.props = A),
      (this.context = U),
      (this.refs = F),
      (this.updater = S || X));
  }
  var mt = (K.prototype = new it());
  ((mt.constructor = K), G(mt, Y.prototype), (mt.isPureReactComponent = !0));
  var yt = Array.isArray;
  function H() {}
  var W = { H: null, A: null, T: null, S: null },
    ht = Object.prototype.hasOwnProperty;
  function pt(A, U, S) {
    var I = S.ref;
    return {
      $$typeof: i,
      type: A,
      key: U,
      ref: I !== void 0 ? I : null,
      props: S,
    };
  }
  function Et(A, U) {
    return pt(A.type, U, A.props);
  }
  function tt(A) {
    return typeof A == "object" && A !== null && A.$$typeof === i;
  }
  function $(A) {
    var U = { "=": "=0", ":": "=2" };
    return (
      "$" +
      A.replace(/[=:]/g, function (S) {
        return U[S];
      })
    );
  }
  var _t = /\/+/g;
  function lt(A, U) {
    return typeof A == "object" && A !== null && A.key != null
      ? $("" + A.key)
      : U.toString(36);
  }
  function Q(A) {
    switch (A.status) {
      case "fulfilled":
        return A.value;
      case "rejected":
        throw A.reason;
      default:
        switch (
          (typeof A.status == "string"
            ? A.then(H, H)
            : ((A.status = "pending"),
              A.then(
                function (U) {
                  A.status === "pending" &&
                    ((A.status = "fulfilled"), (A.value = U));
                },
                function (U) {
                  A.status === "pending" &&
                    ((A.status = "rejected"), (A.reason = U));
                },
              )),
          A.status)
        ) {
          case "fulfilled":
            return A.value;
          case "rejected":
            throw A.reason;
        }
    }
    throw A;
  }
  function M(A, U, S, I, ct) {
    var at = typeof A;
    (at === "undefined" || at === "boolean") && (A = null);
    var zt = !1;
    if (A === null) zt = !0;
    else
      switch (at) {
        case "bigint":
        case "string":
        case "number":
          zt = !0;
          break;
        case "object":
          switch (A.$$typeof) {
            case i:
            case u:
              zt = !0;
              break;
            case b:
              return ((zt = A._init), M(zt(A._payload), U, S, I, ct));
          }
      }
    if (zt)
      return (
        (ct = ct(A)),
        (zt = I === "" ? "." + lt(A, 0) : I),
        yt(ct)
          ? ((S = ""),
            zt != null && (S = zt.replace(_t, "$&/") + "/"),
            M(ct, U, S, "", function (kt) {
              return kt;
            }))
          : ct != null &&
            (tt(ct) &&
              (ct = Et(
                ct,
                S +
                  (ct.key == null || (A && A.key === ct.key)
                    ? ""
                    : ("" + ct.key).replace(_t, "$&/") + "/") +
                  zt,
              )),
            U.push(ct)),
        1
      );
    zt = 0;
    var V = I === "" ? "." : I + ":";
    if (yt(A))
      for (var ut = 0; ut < A.length; ut++)
        ((I = A[ut]), (at = V + lt(I, ut)), (zt += M(I, U, S, at, ct)));
    else if (((ut = x(A)), typeof ut == "function"))
      for (A = ut.call(A), ut = 0; !(I = A.next()).done; )
        ((I = I.value), (at = V + lt(I, ut++)), (zt += M(I, U, S, at, ct)));
    else if (at === "object") {
      if (typeof A.then == "function") return M(Q(A), U, S, I, ct);
      throw (
        (U = String(A)),
        Error(
          "Objects are not valid as a React child (found: " +
            (U === "[object Object]"
              ? "object with keys {" + Object.keys(A).join(", ") + "}"
              : U) +
            "). If you meant to render a collection of children, use an array instead.",
        )
      );
    }
    return zt;
  }
  function B(A, U, S) {
    if (A == null) return A;
    var I = [],
      ct = 0;
    return (
      M(A, I, "", "", function (at) {
        return U.call(S, at, ct++);
      }),
      I
    );
  }
  function P(A) {
    if (A._status === -1) {
      var U = A._result;
      ((U = U()),
        U.then(
          function (S) {
            (A._status === 0 || A._status === -1) &&
              ((A._status = 1), (A._result = S));
          },
          function (S) {
            (A._status === 0 || A._status === -1) &&
              ((A._status = 2), (A._result = S));
          },
        ),
        A._status === -1 && ((A._status = 0), (A._result = U)));
    }
    if (A._status === 1) return A._result.default;
    throw A._result;
  }
  var xt =
      typeof reportError == "function"
        ? reportError
        : function (A) {
            if (
              typeof window == "object" &&
              typeof window.ErrorEvent == "function"
            ) {
              var U = new window.ErrorEvent("error", {
                bubbles: !0,
                cancelable: !0,
                message:
                  typeof A == "object" &&
                  A !== null &&
                  typeof A.message == "string"
                    ? String(A.message)
                    : String(A),
                error: A,
              });
              if (!window.dispatchEvent(U)) return;
            } else if (
              typeof process == "object" &&
              typeof process.emit == "function"
            ) {
              process.emit("uncaughtException", A);
              return;
            }
            console.error(A);
          },
    E = {
      map: B,
      forEach: function (A, U, S) {
        B(
          A,
          function () {
            U.apply(this, arguments);
          },
          S,
        );
      },
      count: function (A) {
        var U = 0;
        return (
          B(A, function () {
            U++;
          }),
          U
        );
      },
      toArray: function (A) {
        return (
          B(A, function (U) {
            return U;
          }) || []
        );
      },
      only: function (A) {
        if (!tt(A))
          throw Error(
            "React.Children.only expected to receive a single React element child.",
          );
        return A;
      },
    };
  return (
    (dt.Activity = v),
    (dt.Children = E),
    (dt.Component = Y),
    (dt.Fragment = r),
    (dt.Profiler = f),
    (dt.PureComponent = K),
    (dt.StrictMode = c),
    (dt.Suspense = y),
    (dt.__CLIENT_INTERNALS_DO_NOT_USE_OR_WARN_USERS_THEY_CANNOT_UPGRADE = W),
    (dt.__COMPILER_RUNTIME = {
      __proto__: null,
      c: function (A) {
        return W.H.useMemoCache(A);
      },
    }),
    (dt.cache = function (A) {
      return function () {
        return A.apply(null, arguments);
      };
    }),
    (dt.cacheSignal = function () {
      return null;
    }),
    (dt.cloneElement = function (A, U, S) {
      if (A == null)
        throw Error(
          "The argument must be a React element, but you passed " + A + ".",
        );
      var I = G({}, A.props),
        ct = A.key;
      if (U != null)
        for (at in (U.key !== void 0 && (ct = "" + U.key), U))
          !ht.call(U, at) ||
            at === "key" ||
            at === "__self" ||
            at === "__source" ||
            (at === "ref" && U.ref === void 0) ||
            (I[at] = U[at]);
      var at = arguments.length - 2;
      if (at === 1) I.children = S;
      else if (1 < at) {
        for (var zt = Array(at), V = 0; V < at; V++) zt[V] = arguments[V + 2];
        I.children = zt;
      }
      return pt(A.type, ct, I);
    }),
    (dt.createContext = function (A) {
      return (
        (A = {
          $$typeof: d,
          _currentValue: A,
          _currentValue2: A,
          _threadCount: 0,
          Provider: null,
          Consumer: null,
        }),
        (A.Provider = A),
        (A.Consumer = { $$typeof: s, _context: A }),
        A
      );
    }),
    (dt.createElement = function (A, U, S) {
      var I,
        ct = {},
        at = null;
      if (U != null)
        for (I in (U.key !== void 0 && (at = "" + U.key), U))
          ht.call(U, I) &&
            I !== "key" &&
            I !== "__self" &&
            I !== "__source" &&
            (ct[I] = U[I]);
      var zt = arguments.length - 2;
      if (zt === 1) ct.children = S;
      else if (1 < zt) {
        for (var V = Array(zt), ut = 0; ut < zt; ut++)
          V[ut] = arguments[ut + 2];
        ct.children = V;
      }
      if (A && A.defaultProps)
        for (I in ((zt = A.defaultProps), zt))
          ct[I] === void 0 && (ct[I] = zt[I]);
      return pt(A, at, ct);
    }),
    (dt.createRef = function () {
      return { current: null };
    }),
    (dt.forwardRef = function (A) {
      return { $$typeof: m, render: A };
    }),
    (dt.isValidElement = tt),
    (dt.lazy = function (A) {
      return { $$typeof: b, _payload: { _status: -1, _result: A }, _init: P };
    }),
    (dt.memo = function (A, U) {
      return { $$typeof: p, type: A, compare: U === void 0 ? null : U };
    }),
    (dt.startTransition = function (A) {
      var U = W.T,
        S = {};
      W.T = S;
      try {
        var I = A(),
          ct = W.S;
        (ct !== null && ct(S, I),
          typeof I == "object" &&
            I !== null &&
            typeof I.then == "function" &&
            I.then(H, xt));
      } catch (at) {
        xt(at);
      } finally {
        (U !== null && S.types !== null && (U.types = S.types), (W.T = U));
      }
    }),
    (dt.unstable_useCacheRefresh = function () {
      return W.H.useCacheRefresh();
    }),
    (dt.use = function (A) {
      return W.H.use(A);
    }),
    (dt.useActionState = function (A, U, S) {
      return W.H.useActionState(A, U, S);
    }),
    (dt.useCallback = function (A, U) {
      return W.H.useCallback(A, U);
    }),
    (dt.useContext = function (A) {
      return W.H.useContext(A);
    }),
    (dt.useDebugValue = function () {}),
    (dt.useDeferredValue = function (A, U) {
      return W.H.useDeferredValue(A, U);
    }),
    (dt.useEffect = function (A, U) {
      return W.H.useEffect(A, U);
    }),
    (dt.useEffectEvent = function (A) {
      return W.H.useEffectEvent(A);
    }),
    (dt.useId = function () {
      return W.H.useId();
    }),
    (dt.useImperativeHandle = function (A, U, S) {
      return W.H.useImperativeHandle(A, U, S);
    }),
    (dt.useInsertionEffect = function (A, U) {
      return W.H.useInsertionEffect(A, U);
    }),
    (dt.useLayoutEffect = function (A, U) {
      return W.H.useLayoutEffect(A, U);
    }),
    (dt.useMemo = function (A, U) {
      return W.H.useMemo(A, U);
    }),
    (dt.useOptimistic = function (A, U) {
      return W.H.useOptimistic(A, U);
    }),
    (dt.useReducer = function (A, U, S) {
      return W.H.useReducer(A, U, S);
    }),
    (dt.useRef = function (A) {
      return W.H.useRef(A);
    }),
    (dt.useState = function (A) {
      return W.H.useState(A);
    }),
    (dt.useSyncExternalStore = function (A, U, S) {
      return W.H.useSyncExternalStore(A, U, S);
    }),
    (dt.useTransition = function () {
      return W.H.useTransition();
    }),
    (dt.version = "19.2.3"),
    dt
  );
}
var np;
function Yo() {
  return (np || ((np = 1), (ho.exports = Wy())), ho.exports);
}
var St = Yo(),
  po = { exports: {} },
  oa = {},
  mo = { exports: {} },
  go = {};
/**
 * @license React
 * scheduler.production.js
 *
 * Copyright (c) Meta Platforms, Inc. and affiliates.
 *
 * This source code is licensed under the MIT license found in the
 * LICENSE file in the root directory of this source tree.
 */ var lp;
function $y() {
  return (
    lp ||
      ((lp = 1),
      (function (i) {
        function u(M, B) {
          var P = M.length;
          M.push(B);
          t: for (; 0 < P; ) {
            var xt = (P - 1) >>> 1,
              E = M[xt];
            if (0 < f(E, B)) ((M[xt] = B), (M[P] = E), (P = xt));
            else break t;
          }
        }
        function r(M) {
          return M.length === 0 ? null : M[0];
        }
        function c(M) {
          if (M.length === 0) return null;
          var B = M[0],
            P = M.pop();
          if (P !== B) {
            M[0] = P;
            t: for (var xt = 0, E = M.length, A = E >>> 1; xt < A; ) {
              var U = 2 * (xt + 1) - 1,
                S = M[U],
                I = U + 1,
                ct = M[I];
              if (0 > f(S, P))
                I < E && 0 > f(ct, S)
                  ? ((M[xt] = ct), (M[I] = P), (xt = I))
                  : ((M[xt] = S), (M[U] = P), (xt = U));
              else if (I < E && 0 > f(ct, P))
                ((M[xt] = ct), (M[I] = P), (xt = I));
              else break t;
            }
          }
          return B;
        }
        function f(M, B) {
          var P = M.sortIndex - B.sortIndex;
          return P !== 0 ? P : M.id - B.id;
        }
        if (
          ((i.unstable_now = void 0),
          typeof performance == "object" &&
            typeof performance.now == "function")
        ) {
          var s = performance;
          i.unstable_now = function () {
            return s.now();
          };
        } else {
          var d = Date,
            m = d.now();
          i.unstable_now = function () {
            return d.now() - m;
          };
        }
        var y = [],
          p = [],
          b = 1,
          v = null,
          T = 3,
          x = !1,
          X = !1,
          G = !1,
          F = !1,
          Y = typeof setTimeout == "function" ? setTimeout : null,
          it = typeof clearTimeout == "function" ? clearTimeout : null,
          K = typeof setImmediate < "u" ? setImmediate : null;
        function mt(M) {
          for (var B = r(p); B !== null; ) {
            if (B.callback === null) c(p);
            else if (B.startTime <= M)
              (c(p), (B.sortIndex = B.expirationTime), u(y, B));
            else break;
            B = r(p);
          }
        }
        function yt(M) {
          if (((G = !1), mt(M), !X))
            if (r(y) !== null) ((X = !0), H || ((H = !0), $()));
            else {
              var B = r(p);
              B !== null && Q(yt, B.startTime - M);
            }
        }
        var H = !1,
          W = -1,
          ht = 5,
          pt = -1;
        function Et() {
          return F ? !0 : !(i.unstable_now() - pt < ht);
        }
        function tt() {
          if (((F = !1), H)) {
            var M = i.unstable_now();
            pt = M;
            var B = !0;
            try {
              t: {
                ((X = !1), G && ((G = !1), it(W), (W = -1)), (x = !0));
                var P = T;
                try {
                  e: {
                    for (
                      mt(M), v = r(y);
                      v !== null && !(v.expirationTime > M && Et());
                    ) {
                      var xt = v.callback;
                      if (typeof xt == "function") {
                        ((v.callback = null), (T = v.priorityLevel));
                        var E = xt(v.expirationTime <= M);
                        if (((M = i.unstable_now()), typeof E == "function")) {
                          ((v.callback = E), mt(M), (B = !0));
                          break e;
                        }
                        (v === r(y) && c(y), mt(M));
                      } else c(y);
                      v = r(y);
                    }
                    if (v !== null) B = !0;
                    else {
                      var A = r(p);
                      (A !== null && Q(yt, A.startTime - M), (B = !1));
                    }
                  }
                  break t;
                } finally {
                  ((v = null), (T = P), (x = !1));
                }
                B = void 0;
              }
            } finally {
              B ? $() : (H = !1);
            }
          }
        }
        var $;
        if (typeof K == "function")
          $ = function () {
            K(tt);
          };
        else if (typeof MessageChannel < "u") {
          var _t = new MessageChannel(),
            lt = _t.port2;
          ((_t.port1.onmessage = tt),
            ($ = function () {
              lt.postMessage(null);
            }));
        } else
          $ = function () {
            Y(tt, 0);
          };
        function Q(M, B) {
          W = Y(function () {
            M(i.unstable_now());
          }, B);
        }
        ((i.unstable_IdlePriority = 5),
          (i.unstable_ImmediatePriority = 1),
          (i.unstable_LowPriority = 4),
          (i.unstable_NormalPriority = 3),
          (i.unstable_Profiling = null),
          (i.unstable_UserBlockingPriority = 2),
          (i.unstable_cancelCallback = function (M) {
            M.callback = null;
          }),
          (i.unstable_forceFrameRate = function (M) {
            0 > M || 125 < M
              ? console.error(
                  "forceFrameRate takes a positive int between 0 and 125, forcing frame rates higher than 125 fps is not supported",
                )
              : (ht = 0 < M ? Math.floor(1e3 / M) : 5);
          }),
          (i.unstable_getCurrentPriorityLevel = function () {
            return T;
          }),
          (i.unstable_next = function (M) {
            switch (T) {
              case 1:
              case 2:
              case 3:
                var B = 3;
                break;
              default:
                B = T;
            }
            var P = T;
            T = B;
            try {
              return M();
            } finally {
              T = P;
            }
          }),
          (i.unstable_requestPaint = function () {
            F = !0;
          }),
          (i.unstable_runWithPriority = function (M, B) {
            switch (M) {
              case 1:
              case 2:
              case 3:
              case 4:
              case 5:
                break;
              default:
                M = 3;
            }
            var P = T;
            T = M;
            try {
              return B();
            } finally {
              T = P;
            }
          }),
          (i.unstable_scheduleCallback = function (M, B, P) {
            var xt = i.unstable_now();
            switch (
              (typeof P == "object" && P !== null
                ? ((P = P.delay),
                  (P = typeof P == "number" && 0 < P ? xt + P : xt))
                : (P = xt),
              M)
            ) {
              case 1:
                var E = -1;
                break;
              case 2:
                E = 250;
                break;
              case 5:
                E = 1073741823;
                break;
              case 4:
                E = 1e4;
                break;
              default:
                E = 5e3;
            }
            return (
              (E = P + E),
              (M = {
                id: b++,
                callback: B,
                priorityLevel: M,
                startTime: P,
                expirationTime: E,
                sortIndex: -1,
              }),
              P > xt
                ? ((M.sortIndex = P),
                  u(p, M),
                  r(y) === null &&
                    M === r(p) &&
                    (G ? (it(W), (W = -1)) : (G = !0), Q(yt, P - xt)))
                : ((M.sortIndex = E),
                  u(y, M),
                  X || x || ((X = !0), H || ((H = !0), $()))),
              M
            );
          }),
          (i.unstable_shouldYield = Et),
          (i.unstable_wrapCallback = function (M) {
            var B = T;
            return function () {
              var P = T;
              T = B;
              try {
                return M.apply(this, arguments);
              } finally {
                T = P;
              }
            };
          }));
      })(go)),
    go
  );
}
var ip;
function Py() {
  return (ip || ((ip = 1), (mo.exports = $y())), mo.exports);
}
var yo = { exports: {} },
  de = {};
/**
 * @license React
 * react-dom.production.js
 *
 * Copyright (c) Meta Platforms, Inc. and affiliates.
 *
 * This source code is licensed under the MIT license found in the
 * LICENSE file in the root directory of this source tree.
 */ var ap;
function t1() {
  if (ap) return de;
  ap = 1;
  var i = Yo();
  function u(y) {
    var p = "https://react.dev/errors/" + y;
    if (1 < arguments.length) {
      p += "?args[]=" + encodeURIComponent(arguments[1]);
      for (var b = 2; b < arguments.length; b++)
        p += "&args[]=" + encodeURIComponent(arguments[b]);
    }
    return (
      "Minified React error #" +
      y +
      "; visit " +
      p +
      " for the full message or use the non-minified dev environment for full errors and additional helpful warnings."
    );
  }
  function r() {}
  var c = {
      d: {
        f: r,
        r: function () {
          throw Error(u(522));
        },
        D: r,
        C: r,
        L: r,
        m: r,
        X: r,
        S: r,
        M: r,
      },
      p: 0,
      findDOMNode: null,
    },
    f = Symbol.for("react.portal");
  function s(y, p, b) {
    var v =
      3 < arguments.length && arguments[3] !== void 0 ? arguments[3] : null;
    return {
      $$typeof: f,
      key: v == null ? null : "" + v,
      children: y,
      containerInfo: p,
      implementation: b,
    };
  }
  var d = i.__CLIENT_INTERNALS_DO_NOT_USE_OR_WARN_USERS_THEY_CANNOT_UPGRADE;
  function m(y, p) {
    if (y === "font") return "";
    if (typeof p == "string") return p === "use-credentials" ? p : "";
  }
  return (
    (de.__DOM_INTERNALS_DO_NOT_USE_OR_WARN_USERS_THEY_CANNOT_UPGRADE = c),
    (de.createPortal = function (y, p) {
      var b =
        2 < arguments.length && arguments[2] !== void 0 ? arguments[2] : null;
      if (!p || (p.nodeType !== 1 && p.nodeType !== 9 && p.nodeType !== 11))
        throw Error(u(299));
      return s(y, p, null, b);
    }),
    (de.flushSync = function (y) {
      var p = d.T,
        b = c.p;
      try {
        if (((d.T = null), (c.p = 2), y)) return y();
      } finally {
        ((d.T = p), (c.p = b), c.d.f());
      }
    }),
    (de.preconnect = function (y, p) {
      typeof y == "string" &&
        (p
          ? ((p = p.crossOrigin),
            (p =
              typeof p == "string"
                ? p === "use-credentials"
                  ? p
                  : ""
                : void 0))
          : (p = null),
        c.d.C(y, p));
    }),
    (de.prefetchDNS = function (y) {
      typeof y == "string" && c.d.D(y);
    }),
    (de.preinit = function (y, p) {
      if (typeof y == "string" && p && typeof p.as == "string") {
        var b = p.as,
          v = m(b, p.crossOrigin),
          T = typeof p.integrity == "string" ? p.integrity : void 0,
          x = typeof p.fetchPriority == "string" ? p.fetchPriority : void 0;
        b === "style"
          ? c.d.S(y, typeof p.precedence == "string" ? p.precedence : void 0, {
              crossOrigin: v,
              integrity: T,
              fetchPriority: x,
            })
          : b === "script" &&
            c.d.X(y, {
              crossOrigin: v,
              integrity: T,
              fetchPriority: x,
              nonce: typeof p.nonce == "string" ? p.nonce : void 0,
            });
      }
    }),
    (de.preinitModule = function (y, p) {
      if (typeof y == "string")
        if (typeof p == "object" && p !== null) {
          if (p.as == null || p.as === "script") {
            var b = m(p.as, p.crossOrigin);
            c.d.M(y, {
              crossOrigin: b,
              integrity: typeof p.integrity == "string" ? p.integrity : void 0,
              nonce: typeof p.nonce == "string" ? p.nonce : void 0,
            });
          }
        } else p == null && c.d.M(y);
    }),
    (de.preload = function (y, p) {
      if (
        typeof y == "string" &&
        typeof p == "object" &&
        p !== null &&
        typeof p.as == "string"
      ) {
        var b = p.as,
          v = m(b, p.crossOrigin);
        c.d.L(y, b, {
          crossOrigin: v,
          integrity: typeof p.integrity == "string" ? p.integrity : void 0,
          nonce: typeof p.nonce == "string" ? p.nonce : void 0,
          type: typeof p.type == "string" ? p.type : void 0,
          fetchPriority:
            typeof p.fetchPriority == "string" ? p.fetchPriority : void 0,
          referrerPolicy:
            typeof p.referrerPolicy == "string" ? p.referrerPolicy : void 0,
          imageSrcSet:
            typeof p.imageSrcSet == "string" ? p.imageSrcSet : void 0,
          imageSizes: typeof p.imageSizes == "string" ? p.imageSizes : void 0,
          media: typeof p.media == "string" ? p.media : void 0,
        });
      }
    }),
    (de.preloadModule = function (y, p) {
      if (typeof y == "string")
        if (p) {
          var b = m(p.as, p.crossOrigin);
          c.d.m(y, {
            as: typeof p.as == "string" && p.as !== "script" ? p.as : void 0,
            crossOrigin: b,
            integrity: typeof p.integrity == "string" ? p.integrity : void 0,
          });
        } else c.d.m(y);
    }),
    (de.requestFormReset = function (y) {
      c.d.r(y);
    }),
    (de.unstable_batchedUpdates = function (y, p) {
      return y(p);
    }),
    (de.useFormState = function (y, p, b) {
      return d.H.useFormState(y, p, b);
    }),
    (de.useFormStatus = function () {
      return d.H.useHostTransitionStatus();
    }),
    (de.version = "19.2.3"),
    de
  );
}
var up;
function e1() {
  if (up) return yo.exports;
  up = 1;
  function i() {
    if (
      !(
        typeof __REACT_DEVTOOLS_GLOBAL_HOOK__ > "u" ||
        typeof __REACT_DEVTOOLS_GLOBAL_HOOK__.checkDCE != "function"
      )
    )
      try {
        __REACT_DEVTOOLS_GLOBAL_HOOK__.checkDCE(i);
      } catch (u) {
        console.error(u);
      }
  }
  return (i(), (yo.exports = t1()), yo.exports);
}
/**
 * @license React
 * react-dom-client.production.js
 *
 * Copyright (c) Meta Platforms, Inc. and affiliates.
 *
 * This source code is licensed under the MIT license found in the
 * LICENSE file in the root directory of this source tree.
 */ var rp;
function n1() {
  if (rp) return oa;
  rp = 1;
  var i = Py(),
    u = Yo(),
    r = e1();
  function c(t) {
    var e = "https://react.dev/errors/" + t;
    if (1 < arguments.length) {
      e += "?args[]=" + encodeURIComponent(arguments[1]);
      for (var n = 2; n < arguments.length; n++)
        e += "&args[]=" + encodeURIComponent(arguments[n]);
    }
    return (
      "Minified React error #" +
      t +
      "; visit " +
      e +
      " for the full message or use the non-minified dev environment for full errors and additional helpful warnings."
    );
  }
  function f(t) {
    return !(!t || (t.nodeType !== 1 && t.nodeType !== 9 && t.nodeType !== 11));
  }
  function s(t) {
    var e = t,
      n = t;
    if (t.alternate) for (; e.return; ) e = e.return;
    else {
      t = e;
      do ((e = t), (e.flags & 4098) !== 0 && (n = e.return), (t = e.return));
      while (t);
    }
    return e.tag === 3 ? n : null;
  }
  function d(t) {
    if (t.tag === 13) {
      var e = t.memoizedState;
      if (
        (e === null && ((t = t.alternate), t !== null && (e = t.memoizedState)),
        e !== null)
      )
        return e.dehydrated;
    }
    return null;
  }
  function m(t) {
    if (t.tag === 31) {
      var e = t.memoizedState;
      if (
        (e === null && ((t = t.alternate), t !== null && (e = t.memoizedState)),
        e !== null)
      )
        return e.dehydrated;
    }
    return null;
  }
  function y(t) {
    if (s(t) !== t) throw Error(c(188));
  }
  function p(t) {
    var e = t.alternate;
    if (!e) {
      if (((e = s(t)), e === null)) throw Error(c(188));
      return e !== t ? null : t;
    }
    for (var n = t, l = e; ; ) {
      var a = n.return;
      if (a === null) break;
      var o = a.alternate;
      if (o === null) {
        if (((l = a.return), l !== null)) {
          n = l;
          continue;
        }
        break;
      }
      if (a.child === o.child) {
        for (o = a.child; o; ) {
          if (o === n) return (y(a), t);
          if (o === l) return (y(a), e);
          o = o.sibling;
        }
        throw Error(c(188));
      }
      if (n.return !== l.return) ((n = a), (l = o));
      else {
        for (var h = !1, g = a.child; g; ) {
          if (g === n) {
            ((h = !0), (n = a), (l = o));
            break;
          }
          if (g === l) {
            ((h = !0), (l = a), (n = o));
            break;
          }
          g = g.sibling;
        }
        if (!h) {
          for (g = o.child; g; ) {
            if (g === n) {
              ((h = !0), (n = o), (l = a));
              break;
            }
            if (g === l) {
              ((h = !0), (l = o), (n = a));
              break;
            }
            g = g.sibling;
          }
          if (!h) throw Error(c(189));
        }
      }
      if (n.alternate !== l) throw Error(c(190));
    }
    if (n.tag !== 3) throw Error(c(188));
    return n.stateNode.current === n ? t : e;
  }
  function b(t) {
    var e = t.tag;
    if (e === 5 || e === 26 || e === 27 || e === 6) return t;
    for (t = t.child; t !== null; ) {
      if (((e = b(t)), e !== null)) return e;
      t = t.sibling;
    }
    return null;
  }
  var v = Object.assign,
    T = Symbol.for("react.element"),
    x = Symbol.for("react.transitional.element"),
    X = Symbol.for("react.portal"),
    G = Symbol.for("react.fragment"),
    F = Symbol.for("react.strict_mode"),
    Y = Symbol.for("react.profiler"),
    it = Symbol.for("react.consumer"),
    K = Symbol.for("react.context"),
    mt = Symbol.for("react.forward_ref"),
    yt = Symbol.for("react.suspense"),
    H = Symbol.for("react.suspense_list"),
    W = Symbol.for("react.memo"),
    ht = Symbol.for("react.lazy"),
    pt = Symbol.for("react.activity"),
    Et = Symbol.for("react.memo_cache_sentinel"),
    tt = Symbol.iterator;
  function $(t) {
    return t === null || typeof t != "object"
      ? null
      : ((t = (tt && t[tt]) || t["@@iterator"]),
        typeof t == "function" ? t : null);
  }
  var _t = Symbol.for("react.client.reference");
  function lt(t) {
    if (t == null) return null;
    if (typeof t == "function")
      return t.$$typeof === _t ? null : t.displayName || t.name || null;
    if (typeof t == "string") return t;
    switch (t) {
      case G:
        return "Fragment";
      case Y:
        return "Profiler";
      case F:
        return "StrictMode";
      case yt:
        return "Suspense";
      case H:
        return "SuspenseList";
      case pt:
        return "Activity";
    }
    if (typeof t == "object")
      switch (t.$$typeof) {
        case X:
          return "Portal";
        case K:
          return t.displayName || "Context";
        case it:
          return (t._context.displayName || "Context") + ".Consumer";
        case mt:
          var e = t.render;
          return (
            (t = t.displayName),
            t ||
              ((t = e.displayName || e.name || ""),
              (t = t !== "" ? "ForwardRef(" + t + ")" : "ForwardRef")),
            t
          );
        case W:
          return (
            (e = t.displayName || null),
            e !== null ? e : lt(t.type) || "Memo"
          );
        case ht:
          ((e = t._payload), (t = t._init));
          try {
            return lt(t(e));
          } catch {}
      }
    return null;
  }
  var Q = Array.isArray,
    M = u.__CLIENT_INTERNALS_DO_NOT_USE_OR_WARN_USERS_THEY_CANNOT_UPGRADE,
    B = r.__DOM_INTERNALS_DO_NOT_USE_OR_WARN_USERS_THEY_CANNOT_UPGRADE,
    P = { pending: !1, data: null, method: null, action: null },
    xt = [],
    E = -1;
  function A(t) {
    return { current: t };
  }
  function U(t) {
    0 > E || ((t.current = xt[E]), (xt[E] = null), E--);
  }
  function S(t, e) {
    (E++, (xt[E] = t.current), (t.current = e));
  }
  var I = A(null),
    ct = A(null),
    at = A(null),
    zt = A(null);
  function V(t, e) {
    switch ((S(at, e), S(ct, t), S(I, null), e.nodeType)) {
      case 9:
      case 11:
        t = (t = e.documentElement) && (t = t.namespaceURI) ? Ed(t) : 0;
        break;
      default:
        if (((t = e.tagName), (e = e.namespaceURI)))
          ((e = Ed(e)), (t = zd(e, t)));
        else
          switch (t) {
            case "svg":
              t = 1;
              break;
            case "math":
              t = 2;
              break;
            default:
              t = 0;
          }
    }
    (U(I), S(I, t));
  }
  function ut() {
    (U(I), U(ct), U(at));
  }
  function kt(t) {
    t.memoizedState !== null && S(zt, t);
    var e = I.current,
      n = zd(e, t.type);
    e !== n && (S(ct, t), S(I, n));
  }
  function me(t) {
    (ct.current === t && (U(I), U(ct)),
      zt.current === t && (U(zt), (ia._currentValue = P)));
  }
  var mi, Sa;
  function on(t) {
    if (mi === void 0)
      try {
        throw Error();
      } catch (n) {
        var e = n.stack.trim().match(/\n( *(at )?)/);
        ((mi = (e && e[1]) || ""),
          (Sa =
            -1 <
            n.stack.indexOf(`
    at`)
              ? " (<anonymous>)"
              : -1 < n.stack.indexOf("@")
                ? "@unknown:0:0"
                : ""));
      }
    return (
      `
` +
      mi +
      t +
      Sa
    );
  }
  var xl = !1;
  function El(t, e) {
    if (!t || xl) return "";
    xl = !0;
    var n = Error.prepareStackTrace;
    Error.prepareStackTrace = void 0;
    try {
      var l = {
        DetermineComponentFrameRoot: function () {
          try {
            if (e) {
              var q = function () {
                throw Error();
              };
              if (
                (Object.defineProperty(q.prototype, "props", {
                  set: function () {
                    throw Error();
                  },
                }),
                typeof Reflect == "object" && Reflect.construct)
              ) {
                try {
                  Reflect.construct(q, []);
                } catch (w) {
                  var k = w;
                }
                Reflect.construct(t, [], q);
              } else {
                try {
                  q.call();
                } catch (w) {
                  k = w;
                }
                t.call(q.prototype);
              }
            } else {
              try {
                throw Error();
              } catch (w) {
                k = w;
              }
              (q = t()) &&
                typeof q.catch == "function" &&
                q.catch(function () {});
            }
          } catch (w) {
            if (w && k && typeof w.stack == "string") return [w.stack, k.stack];
          }
          return [null, null];
        },
      };
      l.DetermineComponentFrameRoot.displayName = "DetermineComponentFrameRoot";
      var a = Object.getOwnPropertyDescriptor(
        l.DetermineComponentFrameRoot,
        "name",
      );
      a &&
        a.configurable &&
        Object.defineProperty(l.DetermineComponentFrameRoot, "name", {
          value: "DetermineComponentFrameRoot",
        });
      var o = l.DetermineComponentFrameRoot(),
        h = o[0],
        g = o[1];
      if (h && g) {
        var z = h.split(`
`),
          D = g.split(`
`);
        for (
          a = l = 0;
          l < z.length && !z[l].includes("DetermineComponentFrameRoot");
        )
          l++;
        for (; a < D.length && !D[a].includes("DetermineComponentFrameRoot"); )
          a++;
        if (l === z.length || a === D.length)
          for (
            l = z.length - 1, a = D.length - 1;
            1 <= l && 0 <= a && z[l] !== D[a];
          )
            a--;
        for (; 1 <= l && 0 <= a; l--, a--)
          if (z[l] !== D[a]) {
            if (l !== 1 || a !== 1)
              do
                if ((l--, a--, 0 > a || z[l] !== D[a])) {
                  var N =
                    `
` + z[l].replace(" at new ", " at ");
                  return (
                    t.displayName &&
                      N.includes("<anonymous>") &&
                      (N = N.replace("<anonymous>", t.displayName)),
                    N
                  );
                }
              while (1 <= l && 0 <= a);
            break;
          }
      }
    } finally {
      ((xl = !1), (Error.prepareStackTrace = n));
    }
    return (n = t ? t.displayName || t.name : "") ? on(n) : "";
  }
  function xa(t, e) {
    switch (t.tag) {
      case 26:
      case 27:
      case 5:
        return on(t.type);
      case 16:
        return on("Lazy");
      case 13:
        return t.child !== e && e !== null
          ? on("Suspense Fallback")
          : on("Suspense");
      case 19:
        return on("SuspenseList");
      case 0:
      case 15:
        return El(t.type, !1);
      case 11:
        return El(t.type.render, !1);
      case 1:
        return El(t.type, !0);
      case 31:
        return on("Activity");
      default:
        return "";
    }
  }
  function Ea(t) {
    try {
      var e = "",
        n = null;
      do ((e += xa(t, n)), (n = t), (t = t.return));
      while (t);
      return e;
    } catch (l) {
      return (
        `
Error generating stack: ` +
        l.message +
        `
` +
        l.stack
      );
    }
  }
  var zl = Object.prototype.hasOwnProperty,
    Tl = i.unstable_scheduleCallback,
    gi = i.unstable_cancelCallback,
    Iu = i.unstable_shouldYield,
    Wu = i.unstable_requestPaint,
    ge = i.unstable_now,
    $u = i.unstable_getCurrentPriorityLevel,
    j = i.unstable_ImmediatePriority,
    J = i.unstable_UserBlockingPriority,
    ft = i.unstable_NormalPriority,
    Tt = i.unstable_LowPriority,
    Bt = i.unstable_IdlePriority,
    Me = i.log,
    fn = i.unstable_setDisableYieldValue,
    ye = null,
    ie = null;
  function ve(t) {
    if (
      (typeof Me == "function" && fn(t),
      ie && typeof ie.setStrictMode == "function")
    )
      try {
        ie.setStrictMode(ye, t);
      } catch {}
  }
  var Gt = Math.clz32 ? Math.clz32 : Um,
    Dn = Math.log,
    We = Math.LN2;
  function Um(t) {
    return ((t >>>= 0), t === 0 ? 32 : (31 - ((Dn(t) / We) | 0)) | 0);
  }
  var za = 256,
    Ta = 262144,
    Aa = 4194304;
  function nl(t) {
    var e = t & 42;
    if (e !== 0) return e;
    switch (t & -t) {
      case 1:
        return 1;
      case 2:
        return 2;
      case 4:
        return 4;
      case 8:
        return 8;
      case 16:
        return 16;
      case 32:
        return 32;
      case 64:
        return 64;
      case 128:
        return 128;
      case 256:
      case 512:
      case 1024:
      case 2048:
      case 4096:
      case 8192:
      case 16384:
      case 32768:
      case 65536:
      case 131072:
        return t & 261888;
      case 262144:
      case 524288:
      case 1048576:
      case 2097152:
        return t & 3932160;
      case 4194304:
      case 8388608:
      case 16777216:
      case 33554432:
        return t & 62914560;
      case 67108864:
        return 67108864;
      case 134217728:
        return 134217728;
      case 268435456:
        return 268435456;
      case 536870912:
        return 536870912;
      case 1073741824:
        return 0;
      default:
        return t;
    }
  }
  function Ca(t, e, n) {
    var l = t.pendingLanes;
    if (l === 0) return 0;
    var a = 0,
      o = t.suspendedLanes,
      h = t.pingedLanes;
    t = t.warmLanes;
    var g = l & 134217727;
    return (
      g !== 0
        ? ((l = g & ~o),
          l !== 0
            ? (a = nl(l))
            : ((h &= g),
              h !== 0
                ? (a = nl(h))
                : n || ((n = g & ~t), n !== 0 && (a = nl(n)))))
        : ((g = l & ~o),
          g !== 0
            ? (a = nl(g))
            : h !== 0
              ? (a = nl(h))
              : n || ((n = l & ~t), n !== 0 && (a = nl(n)))),
      a === 0
        ? 0
        : e !== 0 &&
            e !== a &&
            (e & o) === 0 &&
            ((o = a & -a),
            (n = e & -e),
            o >= n || (o === 32 && (n & 4194048) !== 0))
          ? e
          : a
    );
  }
  function yi(t, e) {
    return (t.pendingLanes & ~(t.suspendedLanes & ~t.pingedLanes) & e) === 0;
  }
  function Bm(t, e) {
    switch (t) {
      case 1:
      case 2:
      case 4:
      case 8:
      case 64:
        return e + 250;
      case 16:
      case 32:
      case 128:
      case 256:
      case 512:
      case 1024:
      case 2048:
      case 4096:
      case 8192:
      case 16384:
      case 32768:
      case 65536:
      case 131072:
      case 262144:
      case 524288:
      case 1048576:
      case 2097152:
        return e + 5e3;
      case 4194304:
      case 8388608:
      case 16777216:
      case 33554432:
        return -1;
      case 67108864:
      case 134217728:
      case 268435456:
      case 536870912:
      case 1073741824:
        return -1;
      default:
        return -1;
    }
  }
  function nf() {
    var t = Aa;
    return ((Aa <<= 1), (Aa & 62914560) === 0 && (Aa = 4194304), t);
  }
  function Pu(t) {
    for (var e = [], n = 0; 31 > n; n++) e.push(t);
    return e;
  }
  function bi(t, e) {
    ((t.pendingLanes |= e),
      e !== 268435456 &&
        ((t.suspendedLanes = 0), (t.pingedLanes = 0), (t.warmLanes = 0)));
  }
  function jm(t, e, n, l, a, o) {
    var h = t.pendingLanes;
    ((t.pendingLanes = n),
      (t.suspendedLanes = 0),
      (t.pingedLanes = 0),
      (t.warmLanes = 0),
      (t.expiredLanes &= n),
      (t.entangledLanes &= n),
      (t.errorRecoveryDisabledLanes &= n),
      (t.shellSuspendCounter = 0));
    var g = t.entanglements,
      z = t.expirationTimes,
      D = t.hiddenUpdates;
    for (n = h & ~n; 0 < n; ) {
      var N = 31 - Gt(n),
        q = 1 << N;
      ((g[N] = 0), (z[N] = -1));
      var k = D[N];
      if (k !== null)
        for (D[N] = null, N = 0; N < k.length; N++) {
          var w = k[N];
          w !== null && (w.lane &= -536870913);
        }
      n &= ~q;
    }
    (l !== 0 && lf(t, l, 0),
      o !== 0 && a === 0 && t.tag !== 0 && (t.suspendedLanes |= o & ~(h & ~e)));
  }
  function lf(t, e, n) {
    ((t.pendingLanes |= e), (t.suspendedLanes &= ~e));
    var l = 31 - Gt(e);
    ((t.entangledLanes |= e),
      (t.entanglements[l] = t.entanglements[l] | 1073741824 | (n & 261930)));
  }
  function af(t, e) {
    var n = (t.entangledLanes |= e);
    for (t = t.entanglements; n; ) {
      var l = 31 - Gt(n),
        a = 1 << l;
      ((a & e) | (t[l] & e) && (t[l] |= e), (n &= ~a));
    }
  }
  function uf(t, e) {
    var n = e & -e;
    return (
      (n = (n & 42) !== 0 ? 1 : tr(n)),
      (n & (t.suspendedLanes | e)) !== 0 ? 0 : n
    );
  }
  function tr(t) {
    switch (t) {
      case 2:
        t = 1;
        break;
      case 8:
        t = 4;
        break;
      case 32:
        t = 16;
        break;
      case 256:
      case 512:
      case 1024:
      case 2048:
      case 4096:
      case 8192:
      case 16384:
      case 32768:
      case 65536:
      case 131072:
      case 262144:
      case 524288:
      case 1048576:
      case 2097152:
      case 4194304:
      case 8388608:
      case 16777216:
      case 33554432:
        t = 128;
        break;
      case 268435456:
        t = 134217728;
        break;
      default:
        t = 0;
    }
    return t;
  }
  function er(t) {
    return (
      (t &= -t),
      2 < t ? (8 < t ? ((t & 134217727) !== 0 ? 32 : 268435456) : 8) : 2
    );
  }
  function rf() {
    var t = B.p;
    return t !== 0 ? t : ((t = window.event), t === void 0 ? 32 : Zd(t.type));
  }
  function cf(t, e) {
    var n = B.p;
    try {
      return ((B.p = t), e());
    } finally {
      B.p = n;
    }
  }
  var Mn = Math.random().toString(36).slice(2),
    ce = "__reactFiber$" + Mn,
    Se = "__reactProps$" + Mn,
    Al = "__reactContainer$" + Mn,
    nr = "__reactEvents$" + Mn,
    Hm = "__reactListeners$" + Mn,
    Lm = "__reactHandles$" + Mn,
    of = "__reactResources$" + Mn,
    vi = "__reactMarker$" + Mn;
  function lr(t) {
    (delete t[ce], delete t[Se], delete t[nr], delete t[Hm], delete t[Lm]);
  }
  function Cl(t) {
    var e = t[ce];
    if (e) return e;
    for (var n = t.parentNode; n; ) {
      if ((e = n[Al] || n[ce])) {
        if (
          ((n = e.alternate),
          e.child !== null || (n !== null && n.child !== null))
        )
          for (t = Md(t); t !== null; ) {
            if ((n = t[ce])) return n;
            t = Md(t);
          }
        return e;
      }
      ((t = n), (n = t.parentNode));
    }
    return null;
  }
  function _l(t) {
    if ((t = t[ce] || t[Al])) {
      var e = t.tag;
      if (
        e === 5 ||
        e === 6 ||
        e === 13 ||
        e === 31 ||
        e === 26 ||
        e === 27 ||
        e === 3
      )
        return t;
    }
    return null;
  }
  function Si(t) {
    var e = t.tag;
    if (e === 5 || e === 26 || e === 27 || e === 6) return t.stateNode;
    throw Error(c(33));
  }
  function Ol(t) {
    var e = t[of];
    return (
      e ||
        (e = t[of] =
          { hoistableStyles: new Map(), hoistableScripts: new Map() }),
      e
    );
  }
  function ue(t) {
    t[vi] = !0;
  }
  var ff = new Set(),
    sf = {};
  function ll(t, e) {
    (Dl(t, e), Dl(t + "Capture", e));
  }
  function Dl(t, e) {
    for (sf[t] = e, t = 0; t < e.length; t++) ff.add(e[t]);
  }
  var qm = RegExp(
      "^[:A-Z_a-z\\u00C0-\\u00D6\\u00D8-\\u00F6\\u00F8-\\u02FF\\u0370-\\u037D\\u037F-\\u1FFF\\u200C-\\u200D\\u2070-\\u218F\\u2C00-\\u2FEF\\u3001-\\uD7FF\\uF900-\\uFDCF\\uFDF0-\\uFFFD][:A-Z_a-z\\u00C0-\\u00D6\\u00D8-\\u00F6\\u00F8-\\u02FF\\u0370-\\u037D\\u037F-\\u1FFF\\u200C-\\u200D\\u2070-\\u218F\\u2C00-\\u2FEF\\u3001-\\uD7FF\\uF900-\\uFDCF\\uFDF0-\\uFFFD\\-.0-9\\u00B7\\u0300-\\u036F\\u203F-\\u2040]*$",
    ),
    hf = {},
    df = {};
  function Ym(t) {
    return zl.call(df, t)
      ? !0
      : zl.call(hf, t)
        ? !1
        : qm.test(t)
          ? (df[t] = !0)
          : ((hf[t] = !0), !1);
  }
  function _a(t, e, n) {
    if (Ym(e))
      if (n === null) t.removeAttribute(e);
      else {
        switch (typeof n) {
          case "undefined":
          case "function":
          case "symbol":
            t.removeAttribute(e);
            return;
          case "boolean":
            var l = e.toLowerCase().slice(0, 5);
            if (l !== "data-" && l !== "aria-") {
              t.removeAttribute(e);
              return;
            }
        }
        t.setAttribute(e, "" + n);
      }
  }
  function Oa(t, e, n) {
    if (n === null) t.removeAttribute(e);
    else {
      switch (typeof n) {
        case "undefined":
        case "function":
        case "symbol":
        case "boolean":
          t.removeAttribute(e);
          return;
      }
      t.setAttribute(e, "" + n);
    }
  }
  function sn(t, e, n, l) {
    if (l === null) t.removeAttribute(n);
    else {
      switch (typeof l) {
        case "undefined":
        case "function":
        case "symbol":
        case "boolean":
          t.removeAttribute(n);
          return;
      }
      t.setAttributeNS(e, n, "" + l);
    }
  }
  function qe(t) {
    switch (typeof t) {
      case "bigint":
      case "boolean":
      case "number":
      case "string":
      case "undefined":
        return t;
      case "object":
        return t;
      default:
        return "";
    }
  }
  function pf(t) {
    var e = t.type;
    return (
      (t = t.nodeName) &&
      t.toLowerCase() === "input" &&
      (e === "checkbox" || e === "radio")
    );
  }
  function Gm(t, e, n) {
    var l = Object.getOwnPropertyDescriptor(t.constructor.prototype, e);
    if (
      !t.hasOwnProperty(e) &&
      typeof l < "u" &&
      typeof l.get == "function" &&
      typeof l.set == "function"
    ) {
      var a = l.get,
        o = l.set;
      return (
        Object.defineProperty(t, e, {
          configurable: !0,
          get: function () {
            return a.call(this);
          },
          set: function (h) {
            ((n = "" + h), o.call(this, h));
          },
        }),
        Object.defineProperty(t, e, { enumerable: l.enumerable }),
        {
          getValue: function () {
            return n;
          },
          setValue: function (h) {
            n = "" + h;
          },
          stopTracking: function () {
            ((t._valueTracker = null), delete t[e]);
          },
        }
      );
    }
  }
  function ir(t) {
    if (!t._valueTracker) {
      var e = pf(t) ? "checked" : "value";
      t._valueTracker = Gm(t, e, "" + t[e]);
    }
  }
  function mf(t) {
    if (!t) return !1;
    var e = t._valueTracker;
    if (!e) return !0;
    var n = e.getValue(),
      l = "";
    return (
      t && (l = pf(t) ? (t.checked ? "true" : "false") : t.value),
      (t = l),
      t !== n ? (e.setValue(t), !0) : !1
    );
  }
  function Da(t) {
    if (
      ((t = t || (typeof document < "u" ? document : void 0)), typeof t > "u")
    )
      return null;
    try {
      return t.activeElement || t.body;
    } catch {
      return t.body;
    }
  }
  var Xm = /[\n"\\]/g;
  function Ye(t) {
    return t.replace(Xm, function (e) {
      return "\\" + e.charCodeAt(0).toString(16) + " ";
    });
  }
  function ar(t, e, n, l, a, o, h, g) {
    ((t.name = ""),
      h != null &&
      typeof h != "function" &&
      typeof h != "symbol" &&
      typeof h != "boolean"
        ? (t.type = h)
        : t.removeAttribute("type"),
      e != null
        ? h === "number"
          ? ((e === 0 && t.value === "") || t.value != e) &&
            (t.value = "" + qe(e))
          : t.value !== "" + qe(e) && (t.value = "" + qe(e))
        : (h !== "submit" && h !== "reset") || t.removeAttribute("value"),
      e != null
        ? ur(t, h, qe(e))
        : n != null
          ? ur(t, h, qe(n))
          : l != null && t.removeAttribute("value"),
      a == null && o != null && (t.defaultChecked = !!o),
      a != null &&
        (t.checked = a && typeof a != "function" && typeof a != "symbol"),
      g != null &&
      typeof g != "function" &&
      typeof g != "symbol" &&
      typeof g != "boolean"
        ? (t.name = "" + qe(g))
        : t.removeAttribute("name"));
  }
  function gf(t, e, n, l, a, o, h, g) {
    if (
      (o != null &&
        typeof o != "function" &&
        typeof o != "symbol" &&
        typeof o != "boolean" &&
        (t.type = o),
      e != null || n != null)
    ) {
      if (!((o !== "submit" && o !== "reset") || e != null)) {
        ir(t);
        return;
      }
      ((n = n != null ? "" + qe(n) : ""),
        (e = e != null ? "" + qe(e) : n),
        g || e === t.value || (t.value = e),
        (t.defaultValue = e));
    }
    ((l = l ?? a),
      (l = typeof l != "function" && typeof l != "symbol" && !!l),
      (t.checked = g ? t.checked : !!l),
      (t.defaultChecked = !!l),
      h != null &&
        typeof h != "function" &&
        typeof h != "symbol" &&
        typeof h != "boolean" &&
        (t.name = h),
      ir(t));
  }
  function ur(t, e, n) {
    (e === "number" && Da(t.ownerDocument) === t) ||
      t.defaultValue === "" + n ||
      (t.defaultValue = "" + n);
  }
  function Ml(t, e, n, l) {
    if (((t = t.options), e)) {
      e = {};
      for (var a = 0; a < n.length; a++) e["$" + n[a]] = !0;
      for (n = 0; n < t.length; n++)
        ((a = e.hasOwnProperty("$" + t[n].value)),
          t[n].selected !== a && (t[n].selected = a),
          a && l && (t[n].defaultSelected = !0));
    } else {
      for (n = "" + qe(n), e = null, a = 0; a < t.length; a++) {
        if (t[a].value === n) {
          ((t[a].selected = !0), l && (t[a].defaultSelected = !0));
          return;
        }
        e !== null || t[a].disabled || (e = t[a]);
      }
      e !== null && (e.selected = !0);
    }
  }
  function yf(t, e, n) {
    if (
      e != null &&
      ((e = "" + qe(e)), e !== t.value && (t.value = e), n == null)
    ) {
      t.defaultValue !== e && (t.defaultValue = e);
      return;
    }
    t.defaultValue = n != null ? "" + qe(n) : "";
  }
  function bf(t, e, n, l) {
    if (e == null) {
      if (l != null) {
        if (n != null) throw Error(c(92));
        if (Q(l)) {
          if (1 < l.length) throw Error(c(93));
          l = l[0];
        }
        n = l;
      }
      (n == null && (n = ""), (e = n));
    }
    ((n = qe(e)),
      (t.defaultValue = n),
      (l = t.textContent),
      l === n && l !== "" && l !== null && (t.value = l),
      ir(t));
  }
  function kl(t, e) {
    if (e) {
      var n = t.firstChild;
      if (n && n === t.lastChild && n.nodeType === 3) {
        n.nodeValue = e;
        return;
      }
    }
    t.textContent = e;
  }
  var Qm = new Set(
    "animationIterationCount aspectRatio borderImageOutset borderImageSlice borderImageWidth boxFlex boxFlexGroup boxOrdinalGroup columnCount columns flex flexGrow flexPositive flexShrink flexNegative flexOrder gridArea gridRow gridRowEnd gridRowSpan gridRowStart gridColumn gridColumnEnd gridColumnSpan gridColumnStart fontWeight lineClamp lineHeight opacity order orphans scale tabSize widows zIndex zoom fillOpacity floodOpacity stopOpacity strokeDasharray strokeDashoffset strokeMiterlimit strokeOpacity strokeWidth MozAnimationIterationCount MozBoxFlex MozBoxFlexGroup MozLineClamp msAnimationIterationCount msFlex msZoom msFlexGrow msFlexNegative msFlexOrder msFlexPositive msFlexShrink msGridColumn msGridColumnSpan msGridRow msGridRowSpan WebkitAnimationIterationCount WebkitBoxFlex WebKitBoxFlexGroup WebkitBoxOrdinalGroup WebkitColumnCount WebkitColumns WebkitFlex WebkitFlexGrow WebkitFlexPositive WebkitFlexShrink WebkitLineClamp".split(
      " ",
    ),
  );
  function vf(t, e, n) {
    var l = e.indexOf("--") === 0;
    n == null || typeof n == "boolean" || n === ""
      ? l
        ? t.setProperty(e, "")
        : e === "float"
          ? (t.cssFloat = "")
          : (t[e] = "")
      : l
        ? t.setProperty(e, n)
        : typeof n != "number" || n === 0 || Qm.has(e)
          ? e === "float"
            ? (t.cssFloat = n)
            : (t[e] = ("" + n).trim())
          : (t[e] = n + "px");
  }
  function Sf(t, e, n) {
    if (e != null && typeof e != "object") throw Error(c(62));
    if (((t = t.style), n != null)) {
      for (var l in n)
        !n.hasOwnProperty(l) ||
          (e != null && e.hasOwnProperty(l)) ||
          (l.indexOf("--") === 0
            ? t.setProperty(l, "")
            : l === "float"
              ? (t.cssFloat = "")
              : (t[l] = ""));
      for (var a in e)
        ((l = e[a]), e.hasOwnProperty(a) && n[a] !== l && vf(t, a, l));
    } else for (var o in e) e.hasOwnProperty(o) && vf(t, o, e[o]);
  }
  function rr(t) {
    if (t.indexOf("-") === -1) return !1;
    switch (t) {
      case "annotation-xml":
      case "color-profile":
      case "font-face":
      case "font-face-src":
      case "font-face-uri":
      case "font-face-format":
      case "font-face-name":
      case "missing-glyph":
        return !1;
      default:
        return !0;
    }
  }
  var Vm = new Map([
      ["acceptCharset", "accept-charset"],
      ["htmlFor", "for"],
      ["httpEquiv", "http-equiv"],
      ["crossOrigin", "crossorigin"],
      ["accentHeight", "accent-height"],
      ["alignmentBaseline", "alignment-baseline"],
      ["arabicForm", "arabic-form"],
      ["baselineShift", "baseline-shift"],
      ["capHeight", "cap-height"],
      ["clipPath", "clip-path"],
      ["clipRule", "clip-rule"],
      ["colorInterpolation", "color-interpolation"],
      ["colorInterpolationFilters", "color-interpolation-filters"],
      ["colorProfile", "color-profile"],
      ["colorRendering", "color-rendering"],
      ["dominantBaseline", "dominant-baseline"],
      ["enableBackground", "enable-background"],
      ["fillOpacity", "fill-opacity"],
      ["fillRule", "fill-rule"],
      ["floodColor", "flood-color"],
      ["floodOpacity", "flood-opacity"],
      ["fontFamily", "font-family"],
      ["fontSize", "font-size"],
      ["fontSizeAdjust", "font-size-adjust"],
      ["fontStretch", "font-stretch"],
      ["fontStyle", "font-style"],
      ["fontVariant", "font-variant"],
      ["fontWeight", "font-weight"],
      ["glyphName", "glyph-name"],
      ["glyphOrientationHorizontal", "glyph-orientation-horizontal"],
      ["glyphOrientationVertical", "glyph-orientation-vertical"],
      ["horizAdvX", "horiz-adv-x"],
      ["horizOriginX", "horiz-origin-x"],
      ["imageRendering", "image-rendering"],
      ["letterSpacing", "letter-spacing"],
      ["lightingColor", "lighting-color"],
      ["markerEnd", "marker-end"],
      ["markerMid", "marker-mid"],
      ["markerStart", "marker-start"],
      ["overlinePosition", "overline-position"],
      ["overlineThickness", "overline-thickness"],
      ["paintOrder", "paint-order"],
      ["panose-1", "panose-1"],
      ["pointerEvents", "pointer-events"],
      ["renderingIntent", "rendering-intent"],
      ["shapeRendering", "shape-rendering"],
      ["stopColor", "stop-color"],
      ["stopOpacity", "stop-opacity"],
      ["strikethroughPosition", "strikethrough-position"],
      ["strikethroughThickness", "strikethrough-thickness"],
      ["strokeDasharray", "stroke-dasharray"],
      ["strokeDashoffset", "stroke-dashoffset"],
      ["strokeLinecap", "stroke-linecap"],
      ["strokeLinejoin", "stroke-linejoin"],
      ["strokeMiterlimit", "stroke-miterlimit"],
      ["strokeOpacity", "stroke-opacity"],
      ["strokeWidth", "stroke-width"],
      ["textAnchor", "text-anchor"],
      ["textDecoration", "text-decoration"],
      ["textRendering", "text-rendering"],
      ["transformOrigin", "transform-origin"],
      ["underlinePosition", "underline-position"],
      ["underlineThickness", "underline-thickness"],
      ["unicodeBidi", "unicode-bidi"],
      ["unicodeRange", "unicode-range"],
      ["unitsPerEm", "units-per-em"],
      ["vAlphabetic", "v-alphabetic"],
      ["vHanging", "v-hanging"],
      ["vIdeographic", "v-ideographic"],
      ["vMathematical", "v-mathematical"],
      ["vectorEffect", "vector-effect"],
      ["vertAdvY", "vert-adv-y"],
      ["vertOriginX", "vert-origin-x"],
      ["vertOriginY", "vert-origin-y"],
      ["wordSpacing", "word-spacing"],
      ["writingMode", "writing-mode"],
      ["xmlnsXlink", "xmlns:xlink"],
      ["xHeight", "x-height"],
    ]),
    Zm =
      /^[\u0000-\u001F ]*j[\r\n\t]*a[\r\n\t]*v[\r\n\t]*a[\r\n\t]*s[\r\n\t]*c[\r\n\t]*r[\r\n\t]*i[\r\n\t]*p[\r\n\t]*t[\r\n\t]*:/i;
  function Ma(t) {
    return Zm.test("" + t)
      ? "javascript:throw new Error('React has blocked a javascript: URL as a security precaution.')"
      : t;
  }
  function hn() {}
  var cr = null;
  function or(t) {
    return (
      (t = t.target || t.srcElement || window),
      t.correspondingUseElement && (t = t.correspondingUseElement),
      t.nodeType === 3 ? t.parentNode : t
    );
  }
  var wl = null,
    Nl = null;
  function xf(t) {
    var e = _l(t);
    if (e && (t = e.stateNode)) {
      var n = t[Se] || null;
      t: switch (((t = e.stateNode), e.type)) {
        case "input":
          if (
            (ar(
              t,
              n.value,
              n.defaultValue,
              n.defaultValue,
              n.checked,
              n.defaultChecked,
              n.type,
              n.name,
            ),
            (e = n.name),
            n.type === "radio" && e != null)
          ) {
            for (n = t; n.parentNode; ) n = n.parentNode;
            for (
              n = n.querySelectorAll(
                'input[name="' + Ye("" + e) + '"][type="radio"]',
              ),
                e = 0;
              e < n.length;
              e++
            ) {
              var l = n[e];
              if (l !== t && l.form === t.form) {
                var a = l[Se] || null;
                if (!a) throw Error(c(90));
                ar(
                  l,
                  a.value,
                  a.defaultValue,
                  a.defaultValue,
                  a.checked,
                  a.defaultChecked,
                  a.type,
                  a.name,
                );
              }
            }
            for (e = 0; e < n.length; e++)
              ((l = n[e]), l.form === t.form && mf(l));
          }
          break t;
        case "textarea":
          yf(t, n.value, n.defaultValue);
          break t;
        case "select":
          ((e = n.value), e != null && Ml(t, !!n.multiple, e, !1));
      }
    }
  }
  var fr = !1;
  function Ef(t, e, n) {
    if (fr) return t(e, n);
    fr = !0;
    try {
      var l = t(e);
      return l;
    } finally {
      if (
        ((fr = !1),
        (wl !== null || Nl !== null) &&
          (yu(), wl && ((e = wl), (t = Nl), (Nl = wl = null), xf(e), t)))
      )
        for (e = 0; e < t.length; e++) xf(t[e]);
    }
  }
  function xi(t, e) {
    var n = t.stateNode;
    if (n === null) return null;
    var l = n[Se] || null;
    if (l === null) return null;
    n = l[e];
    t: switch (e) {
      case "onClick":
      case "onClickCapture":
      case "onDoubleClick":
      case "onDoubleClickCapture":
      case "onMouseDown":
      case "onMouseDownCapture":
      case "onMouseMove":
      case "onMouseMoveCapture":
      case "onMouseUp":
      case "onMouseUpCapture":
      case "onMouseEnter":
        ((l = !l.disabled) ||
          ((t = t.type),
          (l = !(
            t === "button" ||
            t === "input" ||
            t === "select" ||
            t === "textarea"
          ))),
          (t = !l));
        break t;
      default:
        t = !1;
    }
    if (t) return null;
    if (n && typeof n != "function") throw Error(c(231, e, typeof n));
    return n;
  }
  var dn = !(
      typeof window > "u" ||
      typeof window.document > "u" ||
      typeof window.document.createElement > "u"
    ),
    sr = !1;
  if (dn)
    try {
      var Ei = {};
      (Object.defineProperty(Ei, "passive", {
        get: function () {
          sr = !0;
        },
      }),
        window.addEventListener("test", Ei, Ei),
        window.removeEventListener("test", Ei, Ei));
    } catch {
      sr = !1;
    }
  var kn = null,
    hr = null,
    ka = null;
  function zf() {
    if (ka) return ka;
    var t,
      e = hr,
      n = e.length,
      l,
      a = "value" in kn ? kn.value : kn.textContent,
      o = a.length;
    for (t = 0; t < n && e[t] === a[t]; t++);
    var h = n - t;
    for (l = 1; l <= h && e[n - l] === a[o - l]; l++);
    return (ka = a.slice(t, 1 < l ? 1 - l : void 0));
  }
  function wa(t) {
    var e = t.keyCode;
    return (
      "charCode" in t
        ? ((t = t.charCode), t === 0 && e === 13 && (t = 13))
        : (t = e),
      t === 10 && (t = 13),
      32 <= t || t === 13 ? t : 0
    );
  }
  function Na() {
    return !0;
  }
  function Tf() {
    return !1;
  }
  function xe(t) {
    function e(n, l, a, o, h) {
      ((this._reactName = n),
        (this._targetInst = a),
        (this.type = l),
        (this.nativeEvent = o),
        (this.target = h),
        (this.currentTarget = null));
      for (var g in t)
        t.hasOwnProperty(g) && ((n = t[g]), (this[g] = n ? n(o) : o[g]));
      return (
        (this.isDefaultPrevented = (
          o.defaultPrevented != null ? o.defaultPrevented : o.returnValue === !1
        )
          ? Na
          : Tf),
        (this.isPropagationStopped = Tf),
        this
      );
    }
    return (
      v(e.prototype, {
        preventDefault: function () {
          this.defaultPrevented = !0;
          var n = this.nativeEvent;
          n &&
            (n.preventDefault
              ? n.preventDefault()
              : typeof n.returnValue != "unknown" && (n.returnValue = !1),
            (this.isDefaultPrevented = Na));
        },
        stopPropagation: function () {
          var n = this.nativeEvent;
          n &&
            (n.stopPropagation
              ? n.stopPropagation()
              : typeof n.cancelBubble != "unknown" && (n.cancelBubble = !0),
            (this.isPropagationStopped = Na));
        },
        persist: function () {},
        isPersistent: Na,
      }),
      e
    );
  }
  var il = {
      eventPhase: 0,
      bubbles: 0,
      cancelable: 0,
      timeStamp: function (t) {
        return t.timeStamp || Date.now();
      },
      defaultPrevented: 0,
      isTrusted: 0,
    },
    Ra = xe(il),
    zi = v({}, il, { view: 0, detail: 0 }),
    Km = xe(zi),
    dr,
    pr,
    Ti,
    Ua = v({}, zi, {
      screenX: 0,
      screenY: 0,
      clientX: 0,
      clientY: 0,
      pageX: 0,
      pageY: 0,
      ctrlKey: 0,
      shiftKey: 0,
      altKey: 0,
      metaKey: 0,
      getModifierState: gr,
      button: 0,
      buttons: 0,
      relatedTarget: function (t) {
        return t.relatedTarget === void 0
          ? t.fromElement === t.srcElement
            ? t.toElement
            : t.fromElement
          : t.relatedTarget;
      },
      movementX: function (t) {
        return "movementX" in t
          ? t.movementX
          : (t !== Ti &&
              (Ti && t.type === "mousemove"
                ? ((dr = t.screenX - Ti.screenX), (pr = t.screenY - Ti.screenY))
                : (pr = dr = 0),
              (Ti = t)),
            dr);
      },
      movementY: function (t) {
        return "movementY" in t ? t.movementY : pr;
      },
    }),
    Af = xe(Ua),
    Jm = v({}, Ua, { dataTransfer: 0 }),
    Fm = xe(Jm),
    Im = v({}, zi, { relatedTarget: 0 }),
    mr = xe(Im),
    Wm = v({}, il, { animationName: 0, elapsedTime: 0, pseudoElement: 0 }),
    $m = xe(Wm),
    Pm = v({}, il, {
      clipboardData: function (t) {
        return "clipboardData" in t ? t.clipboardData : window.clipboardData;
      },
    }),
    tg = xe(Pm),
    eg = v({}, il, { data: 0 }),
    Cf = xe(eg),
    ng = {
      Esc: "Escape",
      Spacebar: " ",
      Left: "ArrowLeft",
      Up: "ArrowUp",
      Right: "ArrowRight",
      Down: "ArrowDown",
      Del: "Delete",
      Win: "OS",
      Menu: "ContextMenu",
      Apps: "ContextMenu",
      Scroll: "ScrollLock",
      MozPrintableKey: "Unidentified",
    },
    lg = {
      8: "Backspace",
      9: "Tab",
      12: "Clear",
      13: "Enter",
      16: "Shift",
      17: "Control",
      18: "Alt",
      19: "Pause",
      20: "CapsLock",
      27: "Escape",
      32: " ",
      33: "PageUp",
      34: "PageDown",
      35: "End",
      36: "Home",
      37: "ArrowLeft",
      38: "ArrowUp",
      39: "ArrowRight",
      40: "ArrowDown",
      45: "Insert",
      46: "Delete",
      112: "F1",
      113: "F2",
      114: "F3",
      115: "F4",
      116: "F5",
      117: "F6",
      118: "F7",
      119: "F8",
      120: "F9",
      121: "F10",
      122: "F11",
      123: "F12",
      144: "NumLock",
      145: "ScrollLock",
      224: "Meta",
    },
    ig = {
      Alt: "altKey",
      Control: "ctrlKey",
      Meta: "metaKey",
      Shift: "shiftKey",
    };
  function ag(t) {
    var e = this.nativeEvent;
    return e.getModifierState
      ? e.getModifierState(t)
      : (t = ig[t])
        ? !!e[t]
        : !1;
  }
  function gr() {
    return ag;
  }
  var ug = v({}, zi, {
      key: function (t) {
        if (t.key) {
          var e = ng[t.key] || t.key;
          if (e !== "Unidentified") return e;
        }
        return t.type === "keypress"
          ? ((t = wa(t)), t === 13 ? "Enter" : String.fromCharCode(t))
          : t.type === "keydown" || t.type === "keyup"
            ? lg[t.keyCode] || "Unidentified"
            : "";
      },
      code: 0,
      location: 0,
      ctrlKey: 0,
      shiftKey: 0,
      altKey: 0,
      metaKey: 0,
      repeat: 0,
      locale: 0,
      getModifierState: gr,
      charCode: function (t) {
        return t.type === "keypress" ? wa(t) : 0;
      },
      keyCode: function (t) {
        return t.type === "keydown" || t.type === "keyup" ? t.keyCode : 0;
      },
      which: function (t) {
        return t.type === "keypress"
          ? wa(t)
          : t.type === "keydown" || t.type === "keyup"
            ? t.keyCode
            : 0;
      },
    }),
    rg = xe(ug),
    cg = v({}, Ua, {
      pointerId: 0,
      width: 0,
      height: 0,
      pressure: 0,
      tangentialPressure: 0,
      tiltX: 0,
      tiltY: 0,
      twist: 0,
      pointerType: 0,
      isPrimary: 0,
    }),
    _f = xe(cg),
    og = v({}, zi, {
      touches: 0,
      targetTouches: 0,
      changedTouches: 0,
      altKey: 0,
      metaKey: 0,
      ctrlKey: 0,
      shiftKey: 0,
      getModifierState: gr,
    }),
    fg = xe(og),
    sg = v({}, il, { propertyName: 0, elapsedTime: 0, pseudoElement: 0 }),
    hg = xe(sg),
    dg = v({}, Ua, {
      deltaX: function (t) {
        return "deltaX" in t
          ? t.deltaX
          : "wheelDeltaX" in t
            ? -t.wheelDeltaX
            : 0;
      },
      deltaY: function (t) {
        return "deltaY" in t
          ? t.deltaY
          : "wheelDeltaY" in t
            ? -t.wheelDeltaY
            : "wheelDelta" in t
              ? -t.wheelDelta
              : 0;
      },
      deltaZ: 0,
      deltaMode: 0,
    }),
    pg = xe(dg),
    mg = v({}, il, { newState: 0, oldState: 0 }),
    gg = xe(mg),
    yg = [9, 13, 27, 32],
    yr = dn && "CompositionEvent" in window,
    Ai = null;
  dn && "documentMode" in document && (Ai = document.documentMode);
  var bg = dn && "TextEvent" in window && !Ai,
    Of = dn && (!yr || (Ai && 8 < Ai && 11 >= Ai)),
    Df = " ",
    Mf = !1;
  function kf(t, e) {
    switch (t) {
      case "keyup":
        return yg.indexOf(e.keyCode) !== -1;
      case "keydown":
        return e.keyCode !== 229;
      case "keypress":
      case "mousedown":
      case "focusout":
        return !0;
      default:
        return !1;
    }
  }
  function wf(t) {
    return (
      (t = t.detail),
      typeof t == "object" && "data" in t ? t.data : null
    );
  }
  var Rl = !1;
  function vg(t, e) {
    switch (t) {
      case "compositionend":
        return wf(e);
      case "keypress":
        return e.which !== 32 ? null : ((Mf = !0), Df);
      case "textInput":
        return ((t = e.data), t === Df && Mf ? null : t);
      default:
        return null;
    }
  }
  function Sg(t, e) {
    if (Rl)
      return t === "compositionend" || (!yr && kf(t, e))
        ? ((t = zf()), (ka = hr = kn = null), (Rl = !1), t)
        : null;
    switch (t) {
      case "paste":
        return null;
      case "keypress":
        if (!(e.ctrlKey || e.altKey || e.metaKey) || (e.ctrlKey && e.altKey)) {
          if (e.char && 1 < e.char.length) return e.char;
          if (e.which) return String.fromCharCode(e.which);
        }
        return null;
      case "compositionend":
        return Of && e.locale !== "ko" ? null : e.data;
      default:
        return null;
    }
  }
  var xg = {
    color: !0,
    date: !0,
    datetime: !0,
    "datetime-local": !0,
    email: !0,
    month: !0,
    number: !0,
    password: !0,
    range: !0,
    search: !0,
    tel: !0,
    text: !0,
    time: !0,
    url: !0,
    week: !0,
  };
  function Nf(t) {
    var e = t && t.nodeName && t.nodeName.toLowerCase();
    return e === "input" ? !!xg[t.type] : e === "textarea";
  }
  function Rf(t, e, n, l) {
    (wl ? (Nl ? Nl.push(l) : (Nl = [l])) : (wl = l),
      (e = Tu(e, "onChange")),
      0 < e.length &&
        ((n = new Ra("onChange", "change", null, n, l)),
        t.push({ event: n, listeners: e })));
  }
  var Ci = null,
    _i = null;
  function Eg(t) {
    gd(t, 0);
  }
  function Ba(t) {
    var e = Si(t);
    if (mf(e)) return t;
  }
  function Uf(t, e) {
    if (t === "change") return e;
  }
  var Bf = !1;
  if (dn) {
    var br;
    if (dn) {
      var vr = "oninput" in document;
      if (!vr) {
        var jf = document.createElement("div");
        (jf.setAttribute("oninput", "return;"),
          (vr = typeof jf.oninput == "function"));
      }
      br = vr;
    } else br = !1;
    Bf = br && (!document.documentMode || 9 < document.documentMode);
  }
  function Hf() {
    Ci && (Ci.detachEvent("onpropertychange", Lf), (_i = Ci = null));
  }
  function Lf(t) {
    if (t.propertyName === "value" && Ba(_i)) {
      var e = [];
      (Rf(e, _i, t, or(t)), Ef(Eg, e));
    }
  }
  function zg(t, e, n) {
    t === "focusin"
      ? (Hf(), (Ci = e), (_i = n), Ci.attachEvent("onpropertychange", Lf))
      : t === "focusout" && Hf();
  }
  function Tg(t) {
    if (t === "selectionchange" || t === "keyup" || t === "keydown")
      return Ba(_i);
  }
  function Ag(t, e) {
    if (t === "click") return Ba(e);
  }
  function Cg(t, e) {
    if (t === "input" || t === "change") return Ba(e);
  }
  function _g(t, e) {
    return (t === e && (t !== 0 || 1 / t === 1 / e)) || (t !== t && e !== e);
  }
  var ke = typeof Object.is == "function" ? Object.is : _g;
  function Oi(t, e) {
    if (ke(t, e)) return !0;
    if (
      typeof t != "object" ||
      t === null ||
      typeof e != "object" ||
      e === null
    )
      return !1;
    var n = Object.keys(t),
      l = Object.keys(e);
    if (n.length !== l.length) return !1;
    for (l = 0; l < n.length; l++) {
      var a = n[l];
      if (!zl.call(e, a) || !ke(t[a], e[a])) return !1;
    }
    return !0;
  }
  function qf(t) {
    for (; t && t.firstChild; ) t = t.firstChild;
    return t;
  }
  function Yf(t, e) {
    var n = qf(t);
    t = 0;
    for (var l; n; ) {
      if (n.nodeType === 3) {
        if (((l = t + n.textContent.length), t <= e && l >= e))
          return { node: n, offset: e - t };
        t = l;
      }
      t: {
        for (; n; ) {
          if (n.nextSibling) {
            n = n.nextSibling;
            break t;
          }
          n = n.parentNode;
        }
        n = void 0;
      }
      n = qf(n);
    }
  }
  function Gf(t, e) {
    return t && e
      ? t === e
        ? !0
        : t && t.nodeType === 3
          ? !1
          : e && e.nodeType === 3
            ? Gf(t, e.parentNode)
            : "contains" in t
              ? t.contains(e)
              : t.compareDocumentPosition
                ? !!(t.compareDocumentPosition(e) & 16)
                : !1
      : !1;
  }
  function Xf(t) {
    t =
      t != null &&
      t.ownerDocument != null &&
      t.ownerDocument.defaultView != null
        ? t.ownerDocument.defaultView
        : window;
    for (var e = Da(t.document); e instanceof t.HTMLIFrameElement; ) {
      try {
        var n = typeof e.contentWindow.location.href == "string";
      } catch {
        n = !1;
      }
      if (n) t = e.contentWindow;
      else break;
      e = Da(t.document);
    }
    return e;
  }
  function Sr(t) {
    var e = t && t.nodeName && t.nodeName.toLowerCase();
    return (
      e &&
      ((e === "input" &&
        (t.type === "text" ||
          t.type === "search" ||
          t.type === "tel" ||
          t.type === "url" ||
          t.type === "password")) ||
        e === "textarea" ||
        t.contentEditable === "true")
    );
  }
  var Og = dn && "documentMode" in document && 11 >= document.documentMode,
    Ul = null,
    xr = null,
    Di = null,
    Er = !1;
  function Qf(t, e, n) {
    var l =
      n.window === n ? n.document : n.nodeType === 9 ? n : n.ownerDocument;
    Er ||
      Ul == null ||
      Ul !== Da(l) ||
      ((l = Ul),
      "selectionStart" in l && Sr(l)
        ? (l = { start: l.selectionStart, end: l.selectionEnd })
        : ((l = (
            (l.ownerDocument && l.ownerDocument.defaultView) ||
            window
          ).getSelection()),
          (l = {
            anchorNode: l.anchorNode,
            anchorOffset: l.anchorOffset,
            focusNode: l.focusNode,
            focusOffset: l.focusOffset,
          })),
      (Di && Oi(Di, l)) ||
        ((Di = l),
        (l = Tu(xr, "onSelect")),
        0 < l.length &&
          ((e = new Ra("onSelect", "select", null, e, n)),
          t.push({ event: e, listeners: l }),
          (e.target = Ul))));
  }
  function al(t, e) {
    var n = {};
    return (
      (n[t.toLowerCase()] = e.toLowerCase()),
      (n["Webkit" + t] = "webkit" + e),
      (n["Moz" + t] = "moz" + e),
      n
    );
  }
  var Bl = {
      animationend: al("Animation", "AnimationEnd"),
      animationiteration: al("Animation", "AnimationIteration"),
      animationstart: al("Animation", "AnimationStart"),
      transitionrun: al("Transition", "TransitionRun"),
      transitionstart: al("Transition", "TransitionStart"),
      transitioncancel: al("Transition", "TransitionCancel"),
      transitionend: al("Transition", "TransitionEnd"),
    },
    zr = {},
    Vf = {};
  dn &&
    ((Vf = document.createElement("div").style),
    "AnimationEvent" in window ||
      (delete Bl.animationend.animation,
      delete Bl.animationiteration.animation,
      delete Bl.animationstart.animation),
    "TransitionEvent" in window || delete Bl.transitionend.transition);
  function ul(t) {
    if (zr[t]) return zr[t];
    if (!Bl[t]) return t;
    var e = Bl[t],
      n;
    for (n in e) if (e.hasOwnProperty(n) && n in Vf) return (zr[t] = e[n]);
    return t;
  }
  var Zf = ul("animationend"),
    Kf = ul("animationiteration"),
    Jf = ul("animationstart"),
    Dg = ul("transitionrun"),
    Mg = ul("transitionstart"),
    kg = ul("transitioncancel"),
    Ff = ul("transitionend"),
    If = new Map(),
    Tr =
      "abort auxClick beforeToggle cancel canPlay canPlayThrough click close contextMenu copy cut drag dragEnd dragEnter dragExit dragLeave dragOver dragStart drop durationChange emptied encrypted ended error gotPointerCapture input invalid keyDown keyPress keyUp load loadedData loadedMetadata loadStart lostPointerCapture mouseDown mouseMove mouseOut mouseOver mouseUp paste pause play playing pointerCancel pointerDown pointerMove pointerOut pointerOver pointerUp progress rateChange reset resize seeked seeking stalled submit suspend timeUpdate touchCancel touchEnd touchStart volumeChange scroll toggle touchMove waiting wheel".split(
        " ",
      );
  Tr.push("scrollEnd");
  function $e(t, e) {
    (If.set(t, e), ll(e, [t]));
  }
  var ja =
      typeof reportError == "function"
        ? reportError
        : function (t) {
            if (
              typeof window == "object" &&
              typeof window.ErrorEvent == "function"
            ) {
              var e = new window.ErrorEvent("error", {
                bubbles: !0,
                cancelable: !0,
                message:
                  typeof t == "object" &&
                  t !== null &&
                  typeof t.message == "string"
                    ? String(t.message)
                    : String(t),
                error: t,
              });
              if (!window.dispatchEvent(e)) return;
            } else if (
              typeof process == "object" &&
              typeof process.emit == "function"
            ) {
              process.emit("uncaughtException", t);
              return;
            }
            console.error(t);
          },
    Ge = [],
    jl = 0,
    Ar = 0;
  function Ha() {
    for (var t = jl, e = (Ar = jl = 0); e < t; ) {
      var n = Ge[e];
      Ge[e++] = null;
      var l = Ge[e];
      Ge[e++] = null;
      var a = Ge[e];
      Ge[e++] = null;
      var o = Ge[e];
      if (((Ge[e++] = null), l !== null && a !== null)) {
        var h = l.pending;
        (h === null ? (a.next = a) : ((a.next = h.next), (h.next = a)),
          (l.pending = a));
      }
      o !== 0 && Wf(n, a, o);
    }
  }
  function La(t, e, n, l) {
    ((Ge[jl++] = t),
      (Ge[jl++] = e),
      (Ge[jl++] = n),
      (Ge[jl++] = l),
      (Ar |= l),
      (t.lanes |= l),
      (t = t.alternate),
      t !== null && (t.lanes |= l));
  }
  function Cr(t, e, n, l) {
    return (La(t, e, n, l), qa(t));
  }
  function rl(t, e) {
    return (La(t, null, null, e), qa(t));
  }
  function Wf(t, e, n) {
    t.lanes |= n;
    var l = t.alternate;
    l !== null && (l.lanes |= n);
    for (var a = !1, o = t.return; o !== null; )
      ((o.childLanes |= n),
        (l = o.alternate),
        l !== null && (l.childLanes |= n),
        o.tag === 22 &&
          ((t = o.stateNode), t === null || t._visibility & 1 || (a = !0)),
        (t = o),
        (o = o.return));
    return t.tag === 3
      ? ((o = t.stateNode),
        a &&
          e !== null &&
          ((a = 31 - Gt(n)),
          (t = o.hiddenUpdates),
          (l = t[a]),
          l === null ? (t[a] = [e]) : l.push(e),
          (e.lane = n | 536870912)),
        o)
      : null;
  }
  function qa(t) {
    if (50 < Wi) throw ((Wi = 0), (Uc = null), Error(c(185)));
    for (var e = t.return; e !== null; ) ((t = e), (e = t.return));
    return t.tag === 3 ? t.stateNode : null;
  }
  var Hl = {};
  function wg(t, e, n, l) {
    ((this.tag = t),
      (this.key = n),
      (this.sibling =
        this.child =
        this.return =
        this.stateNode =
        this.type =
        this.elementType =
          null),
      (this.index = 0),
      (this.refCleanup = this.ref = null),
      (this.pendingProps = e),
      (this.dependencies =
        this.memoizedState =
        this.updateQueue =
        this.memoizedProps =
          null),
      (this.mode = l),
      (this.subtreeFlags = this.flags = 0),
      (this.deletions = null),
      (this.childLanes = this.lanes = 0),
      (this.alternate = null));
  }
  function we(t, e, n, l) {
    return new wg(t, e, n, l);
  }
  function _r(t) {
    return ((t = t.prototype), !(!t || !t.isReactComponent));
  }
  function pn(t, e) {
    var n = t.alternate;
    return (
      n === null
        ? ((n = we(t.tag, e, t.key, t.mode)),
          (n.elementType = t.elementType),
          (n.type = t.type),
          (n.stateNode = t.stateNode),
          (n.alternate = t),
          (t.alternate = n))
        : ((n.pendingProps = e),
          (n.type = t.type),
          (n.flags = 0),
          (n.subtreeFlags = 0),
          (n.deletions = null)),
      (n.flags = t.flags & 65011712),
      (n.childLanes = t.childLanes),
      (n.lanes = t.lanes),
      (n.child = t.child),
      (n.memoizedProps = t.memoizedProps),
      (n.memoizedState = t.memoizedState),
      (n.updateQueue = t.updateQueue),
      (e = t.dependencies),
      (n.dependencies =
        e === null ? null : { lanes: e.lanes, firstContext: e.firstContext }),
      (n.sibling = t.sibling),
      (n.index = t.index),
      (n.ref = t.ref),
      (n.refCleanup = t.refCleanup),
      n
    );
  }
  function $f(t, e) {
    t.flags &= 65011714;
    var n = t.alternate;
    return (
      n === null
        ? ((t.childLanes = 0),
          (t.lanes = e),
          (t.child = null),
          (t.subtreeFlags = 0),
          (t.memoizedProps = null),
          (t.memoizedState = null),
          (t.updateQueue = null),
          (t.dependencies = null),
          (t.stateNode = null))
        : ((t.childLanes = n.childLanes),
          (t.lanes = n.lanes),
          (t.child = n.child),
          (t.subtreeFlags = 0),
          (t.deletions = null),
          (t.memoizedProps = n.memoizedProps),
          (t.memoizedState = n.memoizedState),
          (t.updateQueue = n.updateQueue),
          (t.type = n.type),
          (e = n.dependencies),
          (t.dependencies =
            e === null
              ? null
              : { lanes: e.lanes, firstContext: e.firstContext })),
      t
    );
  }
  function Ya(t, e, n, l, a, o) {
    var h = 0;
    if (((l = t), typeof t == "function")) _r(t) && (h = 1);
    else if (typeof t == "string")
      h = jy(t, n, I.current)
        ? 26
        : t === "html" || t === "head" || t === "body"
          ? 27
          : 5;
    else
      t: switch (t) {
        case pt:
          return (
            (t = we(31, n, e, a)),
            (t.elementType = pt),
            (t.lanes = o),
            t
          );
        case G:
          return cl(n.children, a, o, e);
        case F:
          ((h = 8), (a |= 24));
          break;
        case Y:
          return (
            (t = we(12, n, e, a | 2)),
            (t.elementType = Y),
            (t.lanes = o),
            t
          );
        case yt:
          return (
            (t = we(13, n, e, a)),
            (t.elementType = yt),
            (t.lanes = o),
            t
          );
        case H:
          return ((t = we(19, n, e, a)), (t.elementType = H), (t.lanes = o), t);
        default:
          if (typeof t == "object" && t !== null)
            switch (t.$$typeof) {
              case K:
                h = 10;
                break t;
              case it:
                h = 9;
                break t;
              case mt:
                h = 11;
                break t;
              case W:
                h = 14;
                break t;
              case ht:
                ((h = 16), (l = null));
                break t;
            }
          ((h = 29),
            (n = Error(c(130, t === null ? "null" : typeof t, ""))),
            (l = null));
      }
    return (
      (e = we(h, n, e, a)),
      (e.elementType = t),
      (e.type = l),
      (e.lanes = o),
      e
    );
  }
  function cl(t, e, n, l) {
    return ((t = we(7, t, l, e)), (t.lanes = n), t);
  }
  function Or(t, e, n) {
    return ((t = we(6, t, null, e)), (t.lanes = n), t);
  }
  function Pf(t) {
    var e = we(18, null, null, 0);
    return ((e.stateNode = t), e);
  }
  function Dr(t, e, n) {
    return (
      (e = we(4, t.children !== null ? t.children : [], t.key, e)),
      (e.lanes = n),
      (e.stateNode = {
        containerInfo: t.containerInfo,
        pendingChildren: null,
        implementation: t.implementation,
      }),
      e
    );
  }
  var ts = new WeakMap();
  function Xe(t, e) {
    if (typeof t == "object" && t !== null) {
      var n = ts.get(t);
      return n !== void 0
        ? n
        : ((e = { value: t, source: e, stack: Ea(e) }), ts.set(t, e), e);
    }
    return { value: t, source: e, stack: Ea(e) };
  }
  var Ll = [],
    ql = 0,
    Ga = null,
    Mi = 0,
    Qe = [],
    Ve = 0,
    wn = null,
    en = 1,
    nn = "";
  function mn(t, e) {
    ((Ll[ql++] = Mi), (Ll[ql++] = Ga), (Ga = t), (Mi = e));
  }
  function es(t, e, n) {
    ((Qe[Ve++] = en), (Qe[Ve++] = nn), (Qe[Ve++] = wn), (wn = t));
    var l = en;
    t = nn;
    var a = 32 - Gt(l) - 1;
    ((l &= ~(1 << a)), (n += 1));
    var o = 32 - Gt(e) + a;
    if (30 < o) {
      var h = a - (a % 5);
      ((o = (l & ((1 << h) - 1)).toString(32)),
        (l >>= h),
        (a -= h),
        (en = (1 << (32 - Gt(e) + a)) | (n << a) | l),
        (nn = o + t));
    } else ((en = (1 << o) | (n << a) | l), (nn = t));
  }
  function Mr(t) {
    t.return !== null && (mn(t, 1), es(t, 1, 0));
  }
  function kr(t) {
    for (; t === Ga; )
      ((Ga = Ll[--ql]), (Ll[ql] = null), (Mi = Ll[--ql]), (Ll[ql] = null));
    for (; t === wn; )
      ((wn = Qe[--Ve]),
        (Qe[Ve] = null),
        (nn = Qe[--Ve]),
        (Qe[Ve] = null),
        (en = Qe[--Ve]),
        (Qe[Ve] = null));
  }
  function ns(t, e) {
    ((Qe[Ve++] = en),
      (Qe[Ve++] = nn),
      (Qe[Ve++] = wn),
      (en = e.id),
      (nn = e.overflow),
      (wn = t));
  }
  var oe = null,
    Zt = null,
    Mt = !1,
    Nn = null,
    Ze = !1,
    wr = Error(c(519));
  function Rn(t) {
    var e = Error(
      c(
        418,
        1 < arguments.length && arguments[1] !== void 0 && arguments[1]
          ? "text"
          : "HTML",
        "",
      ),
    );
    throw (ki(Xe(e, t)), wr);
  }
  function ls(t) {
    var e = t.stateNode,
      n = t.type,
      l = t.memoizedProps;
    switch (((e[ce] = t), (e[Se] = l), n)) {
      case "dialog":
        (Ct("cancel", e), Ct("close", e));
        break;
      case "iframe":
      case "object":
      case "embed":
        Ct("load", e);
        break;
      case "video":
      case "audio":
        for (n = 0; n < Pi.length; n++) Ct(Pi[n], e);
        break;
      case "source":
        Ct("error", e);
        break;
      case "img":
      case "image":
      case "link":
        (Ct("error", e), Ct("load", e));
        break;
      case "details":
        Ct("toggle", e);
        break;
      case "input":
        (Ct("invalid", e),
          gf(
            e,
            l.value,
            l.defaultValue,
            l.checked,
            l.defaultChecked,
            l.type,
            l.name,
            !0,
          ));
        break;
      case "select":
        Ct("invalid", e);
        break;
      case "textarea":
        (Ct("invalid", e), bf(e, l.value, l.defaultValue, l.children));
    }
    ((n = l.children),
      (typeof n != "string" && typeof n != "number" && typeof n != "bigint") ||
      e.textContent === "" + n ||
      l.suppressHydrationWarning === !0 ||
      Sd(e.textContent, n)
        ? (l.popover != null && (Ct("beforetoggle", e), Ct("toggle", e)),
          l.onScroll != null && Ct("scroll", e),
          l.onScrollEnd != null && Ct("scrollend", e),
          l.onClick != null && (e.onclick = hn),
          (e = !0))
        : (e = !1),
      e || Rn(t, !0));
  }
  function is(t) {
    for (oe = t.return; oe; )
      switch (oe.tag) {
        case 5:
        case 31:
        case 13:
          Ze = !1;
          return;
        case 27:
        case 3:
          Ze = !0;
          return;
        default:
          oe = oe.return;
      }
  }
  function Yl(t) {
    if (t !== oe) return !1;
    if (!Mt) return (is(t), (Mt = !0), !1);
    var e = t.tag,
      n;
    if (
      ((n = e !== 3 && e !== 27) &&
        ((n = e === 5) &&
          ((n = t.type),
          (n =
            !(n !== "form" && n !== "button") || Ic(t.type, t.memoizedProps))),
        (n = !n)),
      n && Zt && Rn(t),
      is(t),
      e === 13)
    ) {
      if (((t = t.memoizedState), (t = t !== null ? t.dehydrated : null), !t))
        throw Error(c(317));
      Zt = Dd(t);
    } else if (e === 31) {
      if (((t = t.memoizedState), (t = t !== null ? t.dehydrated : null), !t))
        throw Error(c(317));
      Zt = Dd(t);
    } else
      e === 27
        ? ((e = Zt), Jn(t.type) ? ((t = eo), (eo = null), (Zt = t)) : (Zt = e))
        : (Zt = oe ? Je(t.stateNode.nextSibling) : null);
    return !0;
  }
  function ol() {
    ((Zt = oe = null), (Mt = !1));
  }
  function Nr() {
    var t = Nn;
    return (
      t !== null &&
        (Ae === null ? (Ae = t) : Ae.push.apply(Ae, t), (Nn = null)),
      t
    );
  }
  function ki(t) {
    Nn === null ? (Nn = [t]) : Nn.push(t);
  }
  var Rr = A(null),
    fl = null,
    gn = null;
  function Un(t, e, n) {
    (S(Rr, e._currentValue), (e._currentValue = n));
  }
  function yn(t) {
    ((t._currentValue = Rr.current), U(Rr));
  }
  function Ur(t, e, n) {
    for (; t !== null; ) {
      var l = t.alternate;
      if (
        ((t.childLanes & e) !== e
          ? ((t.childLanes |= e), l !== null && (l.childLanes |= e))
          : l !== null && (l.childLanes & e) !== e && (l.childLanes |= e),
        t === n)
      )
        break;
      t = t.return;
    }
  }
  function Br(t, e, n, l) {
    var a = t.child;
    for (a !== null && (a.return = t); a !== null; ) {
      var o = a.dependencies;
      if (o !== null) {
        var h = a.child;
        o = o.firstContext;
        t: for (; o !== null; ) {
          var g = o;
          o = a;
          for (var z = 0; z < e.length; z++)
            if (g.context === e[z]) {
              ((o.lanes |= n),
                (g = o.alternate),
                g !== null && (g.lanes |= n),
                Ur(o.return, n, t),
                l || (h = null));
              break t;
            }
          o = g.next;
        }
      } else if (a.tag === 18) {
        if (((h = a.return), h === null)) throw Error(c(341));
        ((h.lanes |= n),
          (o = h.alternate),
          o !== null && (o.lanes |= n),
          Ur(h, n, t),
          (h = null));
      } else h = a.child;
      if (h !== null) h.return = a;
      else
        for (h = a; h !== null; ) {
          if (h === t) {
            h = null;
            break;
          }
          if (((a = h.sibling), a !== null)) {
            ((a.return = h.return), (h = a));
            break;
          }
          h = h.return;
        }
      a = h;
    }
  }
  function Gl(t, e, n, l) {
    t = null;
    for (var a = e, o = !1; a !== null; ) {
      if (!o) {
        if ((a.flags & 524288) !== 0) o = !0;
        else if ((a.flags & 262144) !== 0) break;
      }
      if (a.tag === 10) {
        var h = a.alternate;
        if (h === null) throw Error(c(387));
        if (((h = h.memoizedProps), h !== null)) {
          var g = a.type;
          ke(a.pendingProps.value, h.value) ||
            (t !== null ? t.push(g) : (t = [g]));
        }
      } else if (a === zt.current) {
        if (((h = a.alternate), h === null)) throw Error(c(387));
        h.memoizedState.memoizedState !== a.memoizedState.memoizedState &&
          (t !== null ? t.push(ia) : (t = [ia]));
      }
      a = a.return;
    }
    (t !== null && Br(e, t, n, l), (e.flags |= 262144));
  }
  function Xa(t) {
    for (t = t.firstContext; t !== null; ) {
      if (!ke(t.context._currentValue, t.memoizedValue)) return !0;
      t = t.next;
    }
    return !1;
  }
  function sl(t) {
    ((fl = t),
      (gn = null),
      (t = t.dependencies),
      t !== null && (t.firstContext = null));
  }
  function fe(t) {
    return as(fl, t);
  }
  function Qa(t, e) {
    return (fl === null && sl(t), as(t, e));
  }
  function as(t, e) {
    var n = e._currentValue;
    if (((e = { context: e, memoizedValue: n, next: null }), gn === null)) {
      if (t === null) throw Error(c(308));
      ((gn = e),
        (t.dependencies = { lanes: 0, firstContext: e }),
        (t.flags |= 524288));
    } else gn = gn.next = e;
    return n;
  }
  var Ng =
      typeof AbortController < "u"
        ? AbortController
        : function () {
            var t = [],
              e = (this.signal = {
                aborted: !1,
                addEventListener: function (n, l) {
                  t.push(l);
                },
              });
            this.abort = function () {
              ((e.aborted = !0),
                t.forEach(function (n) {
                  return n();
                }));
            };
          },
    Rg = i.unstable_scheduleCallback,
    Ug = i.unstable_NormalPriority,
    Pt = {
      $$typeof: K,
      Consumer: null,
      Provider: null,
      _currentValue: null,
      _currentValue2: null,
      _threadCount: 0,
    };
  function jr() {
    return { controller: new Ng(), data: new Map(), refCount: 0 };
  }
  function wi(t) {
    (t.refCount--,
      t.refCount === 0 &&
        Rg(Ug, function () {
          t.controller.abort();
        }));
  }
  var Ni = null,
    Hr = 0,
    Xl = 0,
    Ql = null;
  function Bg(t, e) {
    if (Ni === null) {
      var n = (Ni = []);
      ((Hr = 0),
        (Xl = Yc()),
        (Ql = {
          status: "pending",
          value: void 0,
          then: function (l) {
            n.push(l);
          },
        }));
    }
    return (Hr++, e.then(us, us), e);
  }
  function us() {
    if (--Hr === 0 && Ni !== null) {
      Ql !== null && (Ql.status = "fulfilled");
      var t = Ni;
      ((Ni = null), (Xl = 0), (Ql = null));
      for (var e = 0; e < t.length; e++) (0, t[e])();
    }
  }
  function jg(t, e) {
    var n = [],
      l = {
        status: "pending",
        value: null,
        reason: null,
        then: function (a) {
          n.push(a);
        },
      };
    return (
      t.then(
        function () {
          ((l.status = "fulfilled"), (l.value = e));
          for (var a = 0; a < n.length; a++) (0, n[a])(e);
        },
        function (a) {
          for (l.status = "rejected", l.reason = a, a = 0; a < n.length; a++)
            (0, n[a])(void 0);
        },
      ),
      l
    );
  }
  var rs = M.S;
  M.S = function (t, e) {
    ((Qh = ge()),
      typeof e == "object" &&
        e !== null &&
        typeof e.then == "function" &&
        Bg(t, e),
      rs !== null && rs(t, e));
  };
  var hl = A(null);
  function Lr() {
    var t = hl.current;
    return t !== null ? t : Xt.pooledCache;
  }
  function Va(t, e) {
    e === null ? S(hl, hl.current) : S(hl, e.pool);
  }
  function cs() {
    var t = Lr();
    return t === null ? null : { parent: Pt._currentValue, pool: t };
  }
  var Vl = Error(c(460)),
    qr = Error(c(474)),
    Za = Error(c(542)),
    Ka = { then: function () {} };
  function os(t) {
    return ((t = t.status), t === "fulfilled" || t === "rejected");
  }
  function fs(t, e, n) {
    switch (
      ((n = t[n]),
      n === void 0 ? t.push(e) : n !== e && (e.then(hn, hn), (e = n)),
      e.status)
    ) {
      case "fulfilled":
        return e.value;
      case "rejected":
        throw ((t = e.reason), hs(t), t);
      default:
        if (typeof e.status == "string") e.then(hn, hn);
        else {
          if (((t = Xt), t !== null && 100 < t.shellSuspendCounter))
            throw Error(c(482));
          ((t = e),
            (t.status = "pending"),
            t.then(
              function (l) {
                if (e.status === "pending") {
                  var a = e;
                  ((a.status = "fulfilled"), (a.value = l));
                }
              },
              function (l) {
                if (e.status === "pending") {
                  var a = e;
                  ((a.status = "rejected"), (a.reason = l));
                }
              },
            ));
        }
        switch (e.status) {
          case "fulfilled":
            return e.value;
          case "rejected":
            throw ((t = e.reason), hs(t), t);
        }
        throw ((pl = e), Vl);
    }
  }
  function dl(t) {
    try {
      var e = t._init;
      return e(t._payload);
    } catch (n) {
      throw n !== null && typeof n == "object" && typeof n.then == "function"
        ? ((pl = n), Vl)
        : n;
    }
  }
  var pl = null;
  function ss() {
    if (pl === null) throw Error(c(459));
    var t = pl;
    return ((pl = null), t);
  }
  function hs(t) {
    if (t === Vl || t === Za) throw Error(c(483));
  }
  var Zl = null,
    Ri = 0;
  function Ja(t) {
    var e = Ri;
    return ((Ri += 1), Zl === null && (Zl = []), fs(Zl, t, e));
  }
  function Ui(t, e) {
    ((e = e.props.ref), (t.ref = e !== void 0 ? e : null));
  }
  function Fa(t, e) {
    throw e.$$typeof === T
      ? Error(c(525))
      : ((t = Object.prototype.toString.call(e)),
        Error(
          c(
            31,
            t === "[object Object]"
              ? "object with keys {" + Object.keys(e).join(", ") + "}"
              : t,
          ),
        ));
  }
  function ds(t) {
    function e(_, C) {
      if (t) {
        var O = _.deletions;
        O === null ? ((_.deletions = [C]), (_.flags |= 16)) : O.push(C);
      }
    }
    function n(_, C) {
      if (!t) return null;
      for (; C !== null; ) (e(_, C), (C = C.sibling));
      return null;
    }
    function l(_) {
      for (var C = new Map(); _ !== null; )
        (_.key !== null ? C.set(_.key, _) : C.set(_.index, _), (_ = _.sibling));
      return C;
    }
    function a(_, C) {
      return ((_ = pn(_, C)), (_.index = 0), (_.sibling = null), _);
    }
    function o(_, C, O) {
      return (
        (_.index = O),
        t
          ? ((O = _.alternate),
            O !== null
              ? ((O = O.index), O < C ? ((_.flags |= 67108866), C) : O)
              : ((_.flags |= 67108866), C))
          : ((_.flags |= 1048576), C)
      );
    }
    function h(_) {
      return (t && _.alternate === null && (_.flags |= 67108866), _);
    }
    function g(_, C, O, L) {
      return C === null || C.tag !== 6
        ? ((C = Or(O, _.mode, L)), (C.return = _), C)
        : ((C = a(C, O)), (C.return = _), C);
    }
    function z(_, C, O, L) {
      var rt = O.type;
      return rt === G
        ? N(_, C, O.props.children, L, O.key)
        : C !== null &&
            (C.elementType === rt ||
              (typeof rt == "object" &&
                rt !== null &&
                rt.$$typeof === ht &&
                dl(rt) === C.type))
          ? ((C = a(C, O.props)), Ui(C, O), (C.return = _), C)
          : ((C = Ya(O.type, O.key, O.props, null, _.mode, L)),
            Ui(C, O),
            (C.return = _),
            C);
    }
    function D(_, C, O, L) {
      return C === null ||
        C.tag !== 4 ||
        C.stateNode.containerInfo !== O.containerInfo ||
        C.stateNode.implementation !== O.implementation
        ? ((C = Dr(O, _.mode, L)), (C.return = _), C)
        : ((C = a(C, O.children || [])), (C.return = _), C);
    }
    function N(_, C, O, L, rt) {
      return C === null || C.tag !== 7
        ? ((C = cl(O, _.mode, L, rt)), (C.return = _), C)
        : ((C = a(C, O)), (C.return = _), C);
    }
    function q(_, C, O) {
      if (
        (typeof C == "string" && C !== "") ||
        typeof C == "number" ||
        typeof C == "bigint"
      )
        return ((C = Or("" + C, _.mode, O)), (C.return = _), C);
      if (typeof C == "object" && C !== null) {
        switch (C.$$typeof) {
          case x:
            return (
              (O = Ya(C.type, C.key, C.props, null, _.mode, O)),
              Ui(O, C),
              (O.return = _),
              O
            );
          case X:
            return ((C = Dr(C, _.mode, O)), (C.return = _), C);
          case ht:
            return ((C = dl(C)), q(_, C, O));
        }
        if (Q(C) || $(C))
          return ((C = cl(C, _.mode, O, null)), (C.return = _), C);
        if (typeof C.then == "function") return q(_, Ja(C), O);
        if (C.$$typeof === K) return q(_, Qa(_, C), O);
        Fa(_, C);
      }
      return null;
    }
    function k(_, C, O, L) {
      var rt = C !== null ? C.key : null;
      if (
        (typeof O == "string" && O !== "") ||
        typeof O == "number" ||
        typeof O == "bigint"
      )
        return rt !== null ? null : g(_, C, "" + O, L);
      if (typeof O == "object" && O !== null) {
        switch (O.$$typeof) {
          case x:
            return O.key === rt ? z(_, C, O, L) : null;
          case X:
            return O.key === rt ? D(_, C, O, L) : null;
          case ht:
            return ((O = dl(O)), k(_, C, O, L));
        }
        if (Q(O) || $(O)) return rt !== null ? null : N(_, C, O, L, null);
        if (typeof O.then == "function") return k(_, C, Ja(O), L);
        if (O.$$typeof === K) return k(_, C, Qa(_, O), L);
        Fa(_, O);
      }
      return null;
    }
    function w(_, C, O, L, rt) {
      if (
        (typeof L == "string" && L !== "") ||
        typeof L == "number" ||
        typeof L == "bigint"
      )
        return ((_ = _.get(O) || null), g(C, _, "" + L, rt));
      if (typeof L == "object" && L !== null) {
        switch (L.$$typeof) {
          case x:
            return (
              (_ = _.get(L.key === null ? O : L.key) || null),
              z(C, _, L, rt)
            );
          case X:
            return (
              (_ = _.get(L.key === null ? O : L.key) || null),
              D(C, _, L, rt)
            );
          case ht:
            return ((L = dl(L)), w(_, C, O, L, rt));
        }
        if (Q(L) || $(L)) return ((_ = _.get(O) || null), N(C, _, L, rt, null));
        if (typeof L.then == "function") return w(_, C, O, Ja(L), rt);
        if (L.$$typeof === K) return w(_, C, O, Qa(C, L), rt);
        Fa(C, L);
      }
      return null;
    }
    function et(_, C, O, L) {
      for (
        var rt = null, wt = null, nt = C, bt = (C = 0), Dt = null;
        nt !== null && bt < O.length;
        bt++
      ) {
        nt.index > bt ? ((Dt = nt), (nt = null)) : (Dt = nt.sibling);
        var Nt = k(_, nt, O[bt], L);
        if (Nt === null) {
          nt === null && (nt = Dt);
          break;
        }
        (t && nt && Nt.alternate === null && e(_, nt),
          (C = o(Nt, C, bt)),
          wt === null ? (rt = Nt) : (wt.sibling = Nt),
          (wt = Nt),
          (nt = Dt));
      }
      if (bt === O.length) return (n(_, nt), Mt && mn(_, bt), rt);
      if (nt === null) {
        for (; bt < O.length; bt++)
          ((nt = q(_, O[bt], L)),
            nt !== null &&
              ((C = o(nt, C, bt)),
              wt === null ? (rt = nt) : (wt.sibling = nt),
              (wt = nt)));
        return (Mt && mn(_, bt), rt);
      }
      for (nt = l(nt); bt < O.length; bt++)
        ((Dt = w(nt, _, bt, O[bt], L)),
          Dt !== null &&
            (t &&
              Dt.alternate !== null &&
              nt.delete(Dt.key === null ? bt : Dt.key),
            (C = o(Dt, C, bt)),
            wt === null ? (rt = Dt) : (wt.sibling = Dt),
            (wt = Dt)));
      return (
        t &&
          nt.forEach(function (Pn) {
            return e(_, Pn);
          }),
        Mt && mn(_, bt),
        rt
      );
    }
    function ot(_, C, O, L) {
      if (O == null) throw Error(c(151));
      for (
        var rt = null,
          wt = null,
          nt = C,
          bt = (C = 0),
          Dt = null,
          Nt = O.next();
        nt !== null && !Nt.done;
        bt++, Nt = O.next()
      ) {
        nt.index > bt ? ((Dt = nt), (nt = null)) : (Dt = nt.sibling);
        var Pn = k(_, nt, Nt.value, L);
        if (Pn === null) {
          nt === null && (nt = Dt);
          break;
        }
        (t && nt && Pn.alternate === null && e(_, nt),
          (C = o(Pn, C, bt)),
          wt === null ? (rt = Pn) : (wt.sibling = Pn),
          (wt = Pn),
          (nt = Dt));
      }
      if (Nt.done) return (n(_, nt), Mt && mn(_, bt), rt);
      if (nt === null) {
        for (; !Nt.done; bt++, Nt = O.next())
          ((Nt = q(_, Nt.value, L)),
            Nt !== null &&
              ((C = o(Nt, C, bt)),
              wt === null ? (rt = Nt) : (wt.sibling = Nt),
              (wt = Nt)));
        return (Mt && mn(_, bt), rt);
      }
      for (nt = l(nt); !Nt.done; bt++, Nt = O.next())
        ((Nt = w(nt, _, bt, Nt.value, L)),
          Nt !== null &&
            (t &&
              Nt.alternate !== null &&
              nt.delete(Nt.key === null ? bt : Nt.key),
            (C = o(Nt, C, bt)),
            wt === null ? (rt = Nt) : (wt.sibling = Nt),
            (wt = Nt)));
      return (
        t &&
          nt.forEach(function (Jy) {
            return e(_, Jy);
          }),
        Mt && mn(_, bt),
        rt
      );
    }
    function Yt(_, C, O, L) {
      if (
        (typeof O == "object" &&
          O !== null &&
          O.type === G &&
          O.key === null &&
          (O = O.props.children),
        typeof O == "object" && O !== null)
      ) {
        switch (O.$$typeof) {
          case x:
            t: {
              for (var rt = O.key; C !== null; ) {
                if (C.key === rt) {
                  if (((rt = O.type), rt === G)) {
                    if (C.tag === 7) {
                      (n(_, C.sibling),
                        (L = a(C, O.props.children)),
                        (L.return = _),
                        (_ = L));
                      break t;
                    }
                  } else if (
                    C.elementType === rt ||
                    (typeof rt == "object" &&
                      rt !== null &&
                      rt.$$typeof === ht &&
                      dl(rt) === C.type)
                  ) {
                    (n(_, C.sibling),
                      (L = a(C, O.props)),
                      Ui(L, O),
                      (L.return = _),
                      (_ = L));
                    break t;
                  }
                  n(_, C);
                  break;
                } else e(_, C);
                C = C.sibling;
              }
              O.type === G
                ? ((L = cl(O.props.children, _.mode, L, O.key)),
                  (L.return = _),
                  (_ = L))
                : ((L = Ya(O.type, O.key, O.props, null, _.mode, L)),
                  Ui(L, O),
                  (L.return = _),
                  (_ = L));
            }
            return h(_);
          case X:
            t: {
              for (rt = O.key; C !== null; ) {
                if (C.key === rt)
                  if (
                    C.tag === 4 &&
                    C.stateNode.containerInfo === O.containerInfo &&
                    C.stateNode.implementation === O.implementation
                  ) {
                    (n(_, C.sibling),
                      (L = a(C, O.children || [])),
                      (L.return = _),
                      (_ = L));
                    break t;
                  } else {
                    n(_, C);
                    break;
                  }
                else e(_, C);
                C = C.sibling;
              }
              ((L = Dr(O, _.mode, L)), (L.return = _), (_ = L));
            }
            return h(_);
          case ht:
            return ((O = dl(O)), Yt(_, C, O, L));
        }
        if (Q(O)) return et(_, C, O, L);
        if ($(O)) {
          if (((rt = $(O)), typeof rt != "function")) throw Error(c(150));
          return ((O = rt.call(O)), ot(_, C, O, L));
        }
        if (typeof O.then == "function") return Yt(_, C, Ja(O), L);
        if (O.$$typeof === K) return Yt(_, C, Qa(_, O), L);
        Fa(_, O);
      }
      return (typeof O == "string" && O !== "") ||
        typeof O == "number" ||
        typeof O == "bigint"
        ? ((O = "" + O),
          C !== null && C.tag === 6
            ? (n(_, C.sibling), (L = a(C, O)), (L.return = _), (_ = L))
            : (n(_, C), (L = Or(O, _.mode, L)), (L.return = _), (_ = L)),
          h(_))
        : n(_, C);
    }
    return function (_, C, O, L) {
      try {
        Ri = 0;
        var rt = Yt(_, C, O, L);
        return ((Zl = null), rt);
      } catch (nt) {
        if (nt === Vl || nt === Za) throw nt;
        var wt = we(29, nt, null, _.mode);
        return ((wt.lanes = L), (wt.return = _), wt);
      }
    };
  }
  var ml = ds(!0),
    ps = ds(!1),
    Bn = !1;
  function Yr(t) {
    t.updateQueue = {
      baseState: t.memoizedState,
      firstBaseUpdate: null,
      lastBaseUpdate: null,
      shared: { pending: null, lanes: 0, hiddenCallbacks: null },
      callbacks: null,
    };
  }
  function Gr(t, e) {
    ((t = t.updateQueue),
      e.updateQueue === t &&
        (e.updateQueue = {
          baseState: t.baseState,
          firstBaseUpdate: t.firstBaseUpdate,
          lastBaseUpdate: t.lastBaseUpdate,
          shared: t.shared,
          callbacks: null,
        }));
  }
  function jn(t) {
    return { lane: t, tag: 0, payload: null, callback: null, next: null };
  }
  function Hn(t, e, n) {
    var l = t.updateQueue;
    if (l === null) return null;
    if (((l = l.shared), (Rt & 2) !== 0)) {
      var a = l.pending;
      return (
        a === null ? (e.next = e) : ((e.next = a.next), (a.next = e)),
        (l.pending = e),
        (e = qa(t)),
        Wf(t, null, n),
        e
      );
    }
    return (La(t, l, e, n), qa(t));
  }
  function Bi(t, e, n) {
    if (
      ((e = e.updateQueue), e !== null && ((e = e.shared), (n & 4194048) !== 0))
    ) {
      var l = e.lanes;
      ((l &= t.pendingLanes), (n |= l), (e.lanes = n), af(t, n));
    }
  }
  function Xr(t, e) {
    var n = t.updateQueue,
      l = t.alternate;
    if (l !== null && ((l = l.updateQueue), n === l)) {
      var a = null,
        o = null;
      if (((n = n.firstBaseUpdate), n !== null)) {
        do {
          var h = {
            lane: n.lane,
            tag: n.tag,
            payload: n.payload,
            callback: null,
            next: null,
          };
          (o === null ? (a = o = h) : (o = o.next = h), (n = n.next));
        } while (n !== null);
        o === null ? (a = o = e) : (o = o.next = e);
      } else a = o = e;
      ((n = {
        baseState: l.baseState,
        firstBaseUpdate: a,
        lastBaseUpdate: o,
        shared: l.shared,
        callbacks: l.callbacks,
      }),
        (t.updateQueue = n));
      return;
    }
    ((t = n.lastBaseUpdate),
      t === null ? (n.firstBaseUpdate = e) : (t.next = e),
      (n.lastBaseUpdate = e));
  }
  var Qr = !1;
  function ji() {
    if (Qr) {
      var t = Ql;
      if (t !== null) throw t;
    }
  }
  function Hi(t, e, n, l) {
    Qr = !1;
    var a = t.updateQueue;
    Bn = !1;
    var o = a.firstBaseUpdate,
      h = a.lastBaseUpdate,
      g = a.shared.pending;
    if (g !== null) {
      a.shared.pending = null;
      var z = g,
        D = z.next;
      ((z.next = null), h === null ? (o = D) : (h.next = D), (h = z));
      var N = t.alternate;
      N !== null &&
        ((N = N.updateQueue),
        (g = N.lastBaseUpdate),
        g !== h &&
          (g === null ? (N.firstBaseUpdate = D) : (g.next = D),
          (N.lastBaseUpdate = z)));
    }
    if (o !== null) {
      var q = a.baseState;
      ((h = 0), (N = D = z = null), (g = o));
      do {
        var k = g.lane & -536870913,
          w = k !== g.lane;
        if (w ? (Ot & k) === k : (l & k) === k) {
          (k !== 0 && k === Xl && (Qr = !0),
            N !== null &&
              (N = N.next =
                {
                  lane: 0,
                  tag: g.tag,
                  payload: g.payload,
                  callback: null,
                  next: null,
                }));
          t: {
            var et = t,
              ot = g;
            k = e;
            var Yt = n;
            switch (ot.tag) {
              case 1:
                if (((et = ot.payload), typeof et == "function")) {
                  q = et.call(Yt, q, k);
                  break t;
                }
                q = et;
                break t;
              case 3:
                et.flags = (et.flags & -65537) | 128;
              case 0:
                if (
                  ((et = ot.payload),
                  (k = typeof et == "function" ? et.call(Yt, q, k) : et),
                  k == null)
                )
                  break t;
                q = v({}, q, k);
                break t;
              case 2:
                Bn = !0;
            }
          }
          ((k = g.callback),
            k !== null &&
              ((t.flags |= 64),
              w && (t.flags |= 8192),
              (w = a.callbacks),
              w === null ? (a.callbacks = [k]) : w.push(k)));
        } else
          ((w = {
            lane: k,
            tag: g.tag,
            payload: g.payload,
            callback: g.callback,
            next: null,
          }),
            N === null ? ((D = N = w), (z = q)) : (N = N.next = w),
            (h |= k));
        if (((g = g.next), g === null)) {
          if (((g = a.shared.pending), g === null)) break;
          ((w = g),
            (g = w.next),
            (w.next = null),
            (a.lastBaseUpdate = w),
            (a.shared.pending = null));
        }
      } while (!0);
      (N === null && (z = q),
        (a.baseState = z),
        (a.firstBaseUpdate = D),
        (a.lastBaseUpdate = N),
        o === null && (a.shared.lanes = 0),
        (Xn |= h),
        (t.lanes = h),
        (t.memoizedState = q));
    }
  }
  function ms(t, e) {
    if (typeof t != "function") throw Error(c(191, t));
    t.call(e);
  }
  function gs(t, e) {
    var n = t.callbacks;
    if (n !== null)
      for (t.callbacks = null, t = 0; t < n.length; t++) ms(n[t], e);
  }
  var Kl = A(null),
    Ia = A(0);
  function ys(t, e) {
    ((t = Cn), S(Ia, t), S(Kl, e), (Cn = t | e.baseLanes));
  }
  function Vr() {
    (S(Ia, Cn), S(Kl, Kl.current));
  }
  function Zr() {
    ((Cn = Ia.current), U(Kl), U(Ia));
  }
  var Ne = A(null),
    Ke = null;
  function Ln(t) {
    var e = t.alternate;
    (S(Wt, Wt.current & 1),
      S(Ne, t),
      Ke === null &&
        (e === null || Kl.current !== null || e.memoizedState !== null) &&
        (Ke = t));
  }
  function Kr(t) {
    (S(Wt, Wt.current), S(Ne, t), Ke === null && (Ke = t));
  }
  function bs(t) {
    t.tag === 22
      ? (S(Wt, Wt.current), S(Ne, t), Ke === null && (Ke = t))
      : qn();
  }
  function qn() {
    (S(Wt, Wt.current), S(Ne, Ne.current));
  }
  function Re(t) {
    (U(Ne), Ke === t && (Ke = null), U(Wt));
  }
  var Wt = A(0);
  function Wa(t) {
    for (var e = t; e !== null; ) {
      if (e.tag === 13) {
        var n = e.memoizedState;
        if (n !== null && ((n = n.dehydrated), n === null || Pc(n) || to(n)))
          return e;
      } else if (
        e.tag === 19 &&
        (e.memoizedProps.revealOrder === "forwards" ||
          e.memoizedProps.revealOrder === "backwards" ||
          e.memoizedProps.revealOrder === "unstable_legacy-backwards" ||
          e.memoizedProps.revealOrder === "together")
      ) {
        if ((e.flags & 128) !== 0) return e;
      } else if (e.child !== null) {
        ((e.child.return = e), (e = e.child));
        continue;
      }
      if (e === t) break;
      for (; e.sibling === null; ) {
        if (e.return === null || e.return === t) return null;
        e = e.return;
      }
      ((e.sibling.return = e.return), (e = e.sibling));
    }
    return null;
  }
  var bn = 0,
    gt = null,
    Lt = null,
    te = null,
    $a = !1,
    Jl = !1,
    gl = !1,
    Pa = 0,
    Li = 0,
    Fl = null,
    Hg = 0;
  function Ft() {
    throw Error(c(321));
  }
  function Jr(t, e) {
    if (e === null) return !1;
    for (var n = 0; n < e.length && n < t.length; n++)
      if (!ke(t[n], e[n])) return !1;
    return !0;
  }
  function Fr(t, e, n, l, a, o) {
    return (
      (bn = o),
      (gt = e),
      (e.memoizedState = null),
      (e.updateQueue = null),
      (e.lanes = 0),
      (M.H = t === null || t.memoizedState === null ? eh : fc),
      (gl = !1),
      (o = n(l, a)),
      (gl = !1),
      Jl && (o = Ss(e, n, l, a)),
      vs(t),
      o
    );
  }
  function vs(t) {
    M.H = Gi;
    var e = Lt !== null && Lt.next !== null;
    if (((bn = 0), (te = Lt = gt = null), ($a = !1), (Li = 0), (Fl = null), e))
      throw Error(c(300));
    t === null ||
      ee ||
      ((t = t.dependencies), t !== null && Xa(t) && (ee = !0));
  }
  function Ss(t, e, n, l) {
    gt = t;
    var a = 0;
    do {
      if ((Jl && (Fl = null), (Li = 0), (Jl = !1), 25 <= a))
        throw Error(c(301));
      if (((a += 1), (te = Lt = null), t.updateQueue != null)) {
        var o = t.updateQueue;
        ((o.lastEffect = null),
          (o.events = null),
          (o.stores = null),
          o.memoCache != null && (o.memoCache.index = 0));
      }
      ((M.H = nh), (o = e(n, l)));
    } while (Jl);
    return o;
  }
  function Lg() {
    var t = M.H,
      e = t.useState()[0];
    return (
      (e = typeof e.then == "function" ? qi(e) : e),
      (t = t.useState()[0]),
      (Lt !== null ? Lt.memoizedState : null) !== t && (gt.flags |= 1024),
      e
    );
  }
  function Ir() {
    var t = Pa !== 0;
    return ((Pa = 0), t);
  }
  function Wr(t, e, n) {
    ((e.updateQueue = t.updateQueue), (e.flags &= -2053), (t.lanes &= ~n));
  }
  function $r(t) {
    if ($a) {
      for (t = t.memoizedState; t !== null; ) {
        var e = t.queue;
        (e !== null && (e.pending = null), (t = t.next));
      }
      $a = !1;
    }
    ((bn = 0), (te = Lt = gt = null), (Jl = !1), (Li = Pa = 0), (Fl = null));
  }
  function be() {
    var t = {
      memoizedState: null,
      baseState: null,
      baseQueue: null,
      queue: null,
      next: null,
    };
    return (te === null ? (gt.memoizedState = te = t) : (te = te.next = t), te);
  }
  function $t() {
    if (Lt === null) {
      var t = gt.alternate;
      t = t !== null ? t.memoizedState : null;
    } else t = Lt.next;
    var e = te === null ? gt.memoizedState : te.next;
    if (e !== null) ((te = e), (Lt = t));
    else {
      if (t === null)
        throw gt.alternate === null ? Error(c(467)) : Error(c(310));
      ((Lt = t),
        (t = {
          memoizedState: Lt.memoizedState,
          baseState: Lt.baseState,
          baseQueue: Lt.baseQueue,
          queue: Lt.queue,
          next: null,
        }),
        te === null ? (gt.memoizedState = te = t) : (te = te.next = t));
    }
    return te;
  }
  function tu() {
    return { lastEffect: null, events: null, stores: null, memoCache: null };
  }
  function qi(t) {
    var e = Li;
    return (
      (Li += 1),
      Fl === null && (Fl = []),
      (t = fs(Fl, t, e)),
      (e = gt),
      (te === null ? e.memoizedState : te.next) === null &&
        ((e = e.alternate),
        (M.H = e === null || e.memoizedState === null ? eh : fc)),
      t
    );
  }
  function eu(t) {
    if (t !== null && typeof t == "object") {
      if (typeof t.then == "function") return qi(t);
      if (t.$$typeof === K) return fe(t);
    }
    throw Error(c(438, String(t)));
  }
  function Pr(t) {
    var e = null,
      n = gt.updateQueue;
    if ((n !== null && (e = n.memoCache), e == null)) {
      var l = gt.alternate;
      l !== null &&
        ((l = l.updateQueue),
        l !== null &&
          ((l = l.memoCache),
          l != null &&
            (e = {
              data: l.data.map(function (a) {
                return a.slice();
              }),
              index: 0,
            })));
    }
    if (
      (e == null && (e = { data: [], index: 0 }),
      n === null && ((n = tu()), (gt.updateQueue = n)),
      (n.memoCache = e),
      (n = e.data[e.index]),
      n === void 0)
    )
      for (n = e.data[e.index] = Array(t), l = 0; l < t; l++) n[l] = Et;
    return (e.index++, n);
  }
  function vn(t, e) {
    return typeof e == "function" ? e(t) : e;
  }
  function nu(t) {
    var e = $t();
    return tc(e, Lt, t);
  }
  function tc(t, e, n) {
    var l = t.queue;
    if (l === null) throw Error(c(311));
    l.lastRenderedReducer = n;
    var a = t.baseQueue,
      o = l.pending;
    if (o !== null) {
      if (a !== null) {
        var h = a.next;
        ((a.next = o.next), (o.next = h));
      }
      ((e.baseQueue = a = o), (l.pending = null));
    }
    if (((o = t.baseState), a === null)) t.memoizedState = o;
    else {
      e = a.next;
      var g = (h = null),
        z = null,
        D = e,
        N = !1;
      do {
        var q = D.lane & -536870913;
        if (q !== D.lane ? (Ot & q) === q : (bn & q) === q) {
          var k = D.revertLane;
          if (k === 0)
            (z !== null &&
              (z = z.next =
                {
                  lane: 0,
                  revertLane: 0,
                  gesture: null,
                  action: D.action,
                  hasEagerState: D.hasEagerState,
                  eagerState: D.eagerState,
                  next: null,
                }),
              q === Xl && (N = !0));
          else if ((bn & k) === k) {
            ((D = D.next), k === Xl && (N = !0));
            continue;
          } else
            ((q = {
              lane: 0,
              revertLane: D.revertLane,
              gesture: null,
              action: D.action,
              hasEagerState: D.hasEagerState,
              eagerState: D.eagerState,
              next: null,
            }),
              z === null ? ((g = z = q), (h = o)) : (z = z.next = q),
              (gt.lanes |= k),
              (Xn |= k));
          ((q = D.action),
            gl && n(o, q),
            (o = D.hasEagerState ? D.eagerState : n(o, q)));
        } else
          ((k = {
            lane: q,
            revertLane: D.revertLane,
            gesture: D.gesture,
            action: D.action,
            hasEagerState: D.hasEagerState,
            eagerState: D.eagerState,
            next: null,
          }),
            z === null ? ((g = z = k), (h = o)) : (z = z.next = k),
            (gt.lanes |= q),
            (Xn |= q));
        D = D.next;
      } while (D !== null && D !== e);
      if (
        (z === null ? (h = o) : (z.next = g),
        !ke(o, t.memoizedState) && ((ee = !0), N && ((n = Ql), n !== null)))
      )
        throw n;
      ((t.memoizedState = o),
        (t.baseState = h),
        (t.baseQueue = z),
        (l.lastRenderedState = o));
    }
    return (a === null && (l.lanes = 0), [t.memoizedState, l.dispatch]);
  }
  function ec(t) {
    var e = $t(),
      n = e.queue;
    if (n === null) throw Error(c(311));
    n.lastRenderedReducer = t;
    var l = n.dispatch,
      a = n.pending,
      o = e.memoizedState;
    if (a !== null) {
      n.pending = null;
      var h = (a = a.next);
      do ((o = t(o, h.action)), (h = h.next));
      while (h !== a);
      (ke(o, e.memoizedState) || (ee = !0),
        (e.memoizedState = o),
        e.baseQueue === null && (e.baseState = o),
        (n.lastRenderedState = o));
    }
    return [o, l];
  }
  function xs(t, e, n) {
    var l = gt,
      a = $t(),
      o = Mt;
    if (o) {
      if (n === void 0) throw Error(c(407));
      n = n();
    } else n = e();
    var h = !ke((Lt || a).memoizedState, n);
    if (
      (h && ((a.memoizedState = n), (ee = !0)),
      (a = a.queue),
      ic(Ts.bind(null, l, a, t), [t]),
      a.getSnapshot !== e || h || (te !== null && te.memoizedState.tag & 1))
    ) {
      if (
        ((l.flags |= 2048),
        Il(9, { destroy: void 0 }, zs.bind(null, l, a, n, e), null),
        Xt === null)
      )
        throw Error(c(349));
      o || (bn & 127) !== 0 || Es(l, e, n);
    }
    return n;
  }
  function Es(t, e, n) {
    ((t.flags |= 16384),
      (t = { getSnapshot: e, value: n }),
      (e = gt.updateQueue),
      e === null
        ? ((e = tu()), (gt.updateQueue = e), (e.stores = [t]))
        : ((n = e.stores), n === null ? (e.stores = [t]) : n.push(t)));
  }
  function zs(t, e, n, l) {
    ((e.value = n), (e.getSnapshot = l), As(e) && Cs(t));
  }
  function Ts(t, e, n) {
    return n(function () {
      As(e) && Cs(t);
    });
  }
  function As(t) {
    var e = t.getSnapshot;
    t = t.value;
    try {
      var n = e();
      return !ke(t, n);
    } catch {
      return !0;
    }
  }
  function Cs(t) {
    var e = rl(t, 2);
    e !== null && Ce(e, t, 2);
  }
  function nc(t) {
    var e = be();
    if (typeof t == "function") {
      var n = t;
      if (((t = n()), gl)) {
        ve(!0);
        try {
          n();
        } finally {
          ve(!1);
        }
      }
    }
    return (
      (e.memoizedState = e.baseState = t),
      (e.queue = {
        pending: null,
        lanes: 0,
        dispatch: null,
        lastRenderedReducer: vn,
        lastRenderedState: t,
      }),
      e
    );
  }
  function _s(t, e, n, l) {
    return ((t.baseState = n), tc(t, Lt, typeof l == "function" ? l : vn));
  }
  function qg(t, e, n, l, a) {
    if (au(t)) throw Error(c(485));
    if (((t = e.action), t !== null)) {
      var o = {
        payload: a,
        action: t,
        next: null,
        isTransition: !0,
        status: "pending",
        value: null,
        reason: null,
        listeners: [],
        then: function (h) {
          o.listeners.push(h);
        },
      };
      (M.T !== null ? n(!0) : (o.isTransition = !1),
        l(o),
        (n = e.pending),
        n === null
          ? ((o.next = e.pending = o), Os(e, o))
          : ((o.next = n.next), (e.pending = n.next = o)));
    }
  }
  function Os(t, e) {
    var n = e.action,
      l = e.payload,
      a = t.state;
    if (e.isTransition) {
      var o = M.T,
        h = {};
      M.T = h;
      try {
        var g = n(a, l),
          z = M.S;
        (z !== null && z(h, g), Ds(t, e, g));
      } catch (D) {
        lc(t, e, D);
      } finally {
        (o !== null && h.types !== null && (o.types = h.types), (M.T = o));
      }
    } else
      try {
        ((o = n(a, l)), Ds(t, e, o));
      } catch (D) {
        lc(t, e, D);
      }
  }
  function Ds(t, e, n) {
    n !== null && typeof n == "object" && typeof n.then == "function"
      ? n.then(
          function (l) {
            Ms(t, e, l);
          },
          function (l) {
            return lc(t, e, l);
          },
        )
      : Ms(t, e, n);
  }
  function Ms(t, e, n) {
    ((e.status = "fulfilled"),
      (e.value = n),
      ks(e),
      (t.state = n),
      (e = t.pending),
      e !== null &&
        ((n = e.next),
        n === e ? (t.pending = null) : ((n = n.next), (e.next = n), Os(t, n))));
  }
  function lc(t, e, n) {
    var l = t.pending;
    if (((t.pending = null), l !== null)) {
      l = l.next;
      do ((e.status = "rejected"), (e.reason = n), ks(e), (e = e.next));
      while (e !== l);
    }
    t.action = null;
  }
  function ks(t) {
    t = t.listeners;
    for (var e = 0; e < t.length; e++) (0, t[e])();
  }
  function ws(t, e) {
    return e;
  }
  function Ns(t, e) {
    if (Mt) {
      var n = Xt.formState;
      if (n !== null) {
        t: {
          var l = gt;
          if (Mt) {
            if (Zt) {
              e: {
                for (var a = Zt, o = Ze; a.nodeType !== 8; ) {
                  if (!o) {
                    a = null;
                    break e;
                  }
                  if (((a = Je(a.nextSibling)), a === null)) {
                    a = null;
                    break e;
                  }
                }
                ((o = a.data), (a = o === "F!" || o === "F" ? a : null));
              }
              if (a) {
                ((Zt = Je(a.nextSibling)), (l = a.data === "F!"));
                break t;
              }
            }
            Rn(l);
          }
          l = !1;
        }
        l && (e = n[0]);
      }
    }
    return (
      (n = be()),
      (n.memoizedState = n.baseState = e),
      (l = {
        pending: null,
        lanes: 0,
        dispatch: null,
        lastRenderedReducer: ws,
        lastRenderedState: e,
      }),
      (n.queue = l),
      (n = $s.bind(null, gt, l)),
      (l.dispatch = n),
      (l = nc(!1)),
      (o = oc.bind(null, gt, !1, l.queue)),
      (l = be()),
      (a = { state: e, dispatch: null, action: t, pending: null }),
      (l.queue = a),
      (n = qg.bind(null, gt, a, o, n)),
      (a.dispatch = n),
      (l.memoizedState = t),
      [e, n, !1]
    );
  }
  function Rs(t) {
    var e = $t();
    return Us(e, Lt, t);
  }
  function Us(t, e, n) {
    if (
      ((e = tc(t, e, ws)[0]),
      (t = nu(vn)[0]),
      typeof e == "object" && e !== null && typeof e.then == "function")
    )
      try {
        var l = qi(e);
      } catch (h) {
        throw h === Vl ? Za : h;
      }
    else l = e;
    e = $t();
    var a = e.queue,
      o = a.dispatch;
    return (
      n !== e.memoizedState &&
        ((gt.flags |= 2048),
        Il(9, { destroy: void 0 }, Yg.bind(null, a, n), null)),
      [l, o, t]
    );
  }
  function Yg(t, e) {
    t.action = e;
  }
  function Bs(t) {
    var e = $t(),
      n = Lt;
    if (n !== null) return Us(e, n, t);
    ($t(), (e = e.memoizedState), (n = $t()));
    var l = n.queue.dispatch;
    return ((n.memoizedState = t), [e, l, !1]);
  }
  function Il(t, e, n, l) {
    return (
      (t = { tag: t, create: n, deps: l, inst: e, next: null }),
      (e = gt.updateQueue),
      e === null && ((e = tu()), (gt.updateQueue = e)),
      (n = e.lastEffect),
      n === null
        ? (e.lastEffect = t.next = t)
        : ((l = n.next), (n.next = t), (t.next = l), (e.lastEffect = t)),
      t
    );
  }
  function js() {
    return $t().memoizedState;
  }
  function lu(t, e, n, l) {
    var a = be();
    ((gt.flags |= t),
      (a.memoizedState = Il(
        1 | e,
        { destroy: void 0 },
        n,
        l === void 0 ? null : l,
      )));
  }
  function iu(t, e, n, l) {
    var a = $t();
    l = l === void 0 ? null : l;
    var o = a.memoizedState.inst;
    Lt !== null && l !== null && Jr(l, Lt.memoizedState.deps)
      ? (a.memoizedState = Il(e, o, n, l))
      : ((gt.flags |= t), (a.memoizedState = Il(1 | e, o, n, l)));
  }
  function Hs(t, e) {
    lu(8390656, 8, t, e);
  }
  function ic(t, e) {
    iu(2048, 8, t, e);
  }
  function Gg(t) {
    gt.flags |= 4;
    var e = gt.updateQueue;
    if (e === null) ((e = tu()), (gt.updateQueue = e), (e.events = [t]));
    else {
      var n = e.events;
      n === null ? (e.events = [t]) : n.push(t);
    }
  }
  function Ls(t) {
    var e = $t().memoizedState;
    return (
      Gg({ ref: e, nextImpl: t }),
      function () {
        if ((Rt & 2) !== 0) throw Error(c(440));
        return e.impl.apply(void 0, arguments);
      }
    );
  }
  function qs(t, e) {
    return iu(4, 2, t, e);
  }
  function Ys(t, e) {
    return iu(4, 4, t, e);
  }
  function Gs(t, e) {
    if (typeof e == "function") {
      t = t();
      var n = e(t);
      return function () {
        typeof n == "function" ? n() : e(null);
      };
    }
    if (e != null)
      return (
        (t = t()),
        (e.current = t),
        function () {
          e.current = null;
        }
      );
  }
  function Xs(t, e, n) {
    ((n = n != null ? n.concat([t]) : null), iu(4, 4, Gs.bind(null, e, t), n));
  }
  function ac() {}
  function Qs(t, e) {
    var n = $t();
    e = e === void 0 ? null : e;
    var l = n.memoizedState;
    return e !== null && Jr(e, l[1]) ? l[0] : ((n.memoizedState = [t, e]), t);
  }
  function Vs(t, e) {
    var n = $t();
    e = e === void 0 ? null : e;
    var l = n.memoizedState;
    if (e !== null && Jr(e, l[1])) return l[0];
    if (((l = t()), gl)) {
      ve(!0);
      try {
        t();
      } finally {
        ve(!1);
      }
    }
    return ((n.memoizedState = [l, e]), l);
  }
  function uc(t, e, n) {
    return n === void 0 || ((bn & 1073741824) !== 0 && (Ot & 261930) === 0)
      ? (t.memoizedState = e)
      : ((t.memoizedState = n), (t = Zh()), (gt.lanes |= t), (Xn |= t), n);
  }
  function Zs(t, e, n, l) {
    return ke(n, e)
      ? n
      : Kl.current !== null
        ? ((t = uc(t, n, l)), ke(t, e) || (ee = !0), t)
        : (bn & 42) === 0 || ((bn & 1073741824) !== 0 && (Ot & 261930) === 0)
          ? ((ee = !0), (t.memoizedState = n))
          : ((t = Zh()), (gt.lanes |= t), (Xn |= t), e);
  }
  function Ks(t, e, n, l, a) {
    var o = B.p;
    B.p = o !== 0 && 8 > o ? o : 8;
    var h = M.T,
      g = {};
    ((M.T = g), oc(t, !1, e, n));
    try {
      var z = a(),
        D = M.S;
      if (
        (D !== null && D(g, z),
        z !== null && typeof z == "object" && typeof z.then == "function")
      ) {
        var N = jg(z, l);
        Yi(t, e, N, je(t));
      } else Yi(t, e, l, je(t));
    } catch (q) {
      Yi(t, e, { then: function () {}, status: "rejected", reason: q }, je());
    } finally {
      ((B.p = o),
        h !== null && g.types !== null && (h.types = g.types),
        (M.T = h));
    }
  }
  function Xg() {}
  function rc(t, e, n, l) {
    if (t.tag !== 5) throw Error(c(476));
    var a = Js(t).queue;
    Ks(
      t,
      a,
      e,
      P,
      n === null
        ? Xg
        : function () {
            return (Fs(t), n(l));
          },
    );
  }
  function Js(t) {
    var e = t.memoizedState;
    if (e !== null) return e;
    e = {
      memoizedState: P,
      baseState: P,
      baseQueue: null,
      queue: {
        pending: null,
        lanes: 0,
        dispatch: null,
        lastRenderedReducer: vn,
        lastRenderedState: P,
      },
      next: null,
    };
    var n = {};
    return (
      (e.next = {
        memoizedState: n,
        baseState: n,
        baseQueue: null,
        queue: {
          pending: null,
          lanes: 0,
          dispatch: null,
          lastRenderedReducer: vn,
          lastRenderedState: n,
        },
        next: null,
      }),
      (t.memoizedState = e),
      (t = t.alternate),
      t !== null && (t.memoizedState = e),
      e
    );
  }
  function Fs(t) {
    var e = Js(t);
    (e.next === null && (e = t.alternate.memoizedState),
      Yi(t, e.next.queue, {}, je()));
  }
  function cc() {
    return fe(ia);
  }
  function Is() {
    return $t().memoizedState;
  }
  function Ws() {
    return $t().memoizedState;
  }
  function Qg(t) {
    for (var e = t.return; e !== null; ) {
      switch (e.tag) {
        case 24:
        case 3:
          var n = je();
          t = jn(n);
          var l = Hn(e, t, n);
          (l !== null && (Ce(l, e, n), Bi(l, e, n)),
            (e = { cache: jr() }),
            (t.payload = e));
          return;
      }
      e = e.return;
    }
  }
  function Vg(t, e, n) {
    var l = je();
    ((n = {
      lane: l,
      revertLane: 0,
      gesture: null,
      action: n,
      hasEagerState: !1,
      eagerState: null,
      next: null,
    }),
      au(t)
        ? Ps(e, n)
        : ((n = Cr(t, e, n, l)), n !== null && (Ce(n, t, l), th(n, e, l))));
  }
  function $s(t, e, n) {
    var l = je();
    Yi(t, e, n, l);
  }
  function Yi(t, e, n, l) {
    var a = {
      lane: l,
      revertLane: 0,
      gesture: null,
      action: n,
      hasEagerState: !1,
      eagerState: null,
      next: null,
    };
    if (au(t)) Ps(e, a);
    else {
      var o = t.alternate;
      if (
        t.lanes === 0 &&
        (o === null || o.lanes === 0) &&
        ((o = e.lastRenderedReducer), o !== null)
      )
        try {
          var h = e.lastRenderedState,
            g = o(h, n);
          if (((a.hasEagerState = !0), (a.eagerState = g), ke(g, h)))
            return (La(t, e, a, 0), Xt === null && Ha(), !1);
        } catch {}
      if (((n = Cr(t, e, a, l)), n !== null))
        return (Ce(n, t, l), th(n, e, l), !0);
    }
    return !1;
  }
  function oc(t, e, n, l) {
    if (
      ((l = {
        lane: 2,
        revertLane: Yc(),
        gesture: null,
        action: l,
        hasEagerState: !1,
        eagerState: null,
        next: null,
      }),
      au(t))
    ) {
      if (e) throw Error(c(479));
    } else ((e = Cr(t, n, l, 2)), e !== null && Ce(e, t, 2));
  }
  function au(t) {
    var e = t.alternate;
    return t === gt || (e !== null && e === gt);
  }
  function Ps(t, e) {
    Jl = $a = !0;
    var n = t.pending;
    (n === null ? (e.next = e) : ((e.next = n.next), (n.next = e)),
      (t.pending = e));
  }
  function th(t, e, n) {
    if ((n & 4194048) !== 0) {
      var l = e.lanes;
      ((l &= t.pendingLanes), (n |= l), (e.lanes = n), af(t, n));
    }
  }
  var Gi = {
    readContext: fe,
    use: eu,
    useCallback: Ft,
    useContext: Ft,
    useEffect: Ft,
    useImperativeHandle: Ft,
    useLayoutEffect: Ft,
    useInsertionEffect: Ft,
    useMemo: Ft,
    useReducer: Ft,
    useRef: Ft,
    useState: Ft,
    useDebugValue: Ft,
    useDeferredValue: Ft,
    useTransition: Ft,
    useSyncExternalStore: Ft,
    useId: Ft,
    useHostTransitionStatus: Ft,
    useFormState: Ft,
    useActionState: Ft,
    useOptimistic: Ft,
    useMemoCache: Ft,
    useCacheRefresh: Ft,
  };
  Gi.useEffectEvent = Ft;
  var eh = {
      readContext: fe,
      use: eu,
      useCallback: function (t, e) {
        return ((be().memoizedState = [t, e === void 0 ? null : e]), t);
      },
      useContext: fe,
      useEffect: Hs,
      useImperativeHandle: function (t, e, n) {
        ((n = n != null ? n.concat([t]) : null),
          lu(4194308, 4, Gs.bind(null, e, t), n));
      },
      useLayoutEffect: function (t, e) {
        return lu(4194308, 4, t, e);
      },
      useInsertionEffect: function (t, e) {
        lu(4, 2, t, e);
      },
      useMemo: function (t, e) {
        var n = be();
        e = e === void 0 ? null : e;
        var l = t();
        if (gl) {
          ve(!0);
          try {
            t();
          } finally {
            ve(!1);
          }
        }
        return ((n.memoizedState = [l, e]), l);
      },
      useReducer: function (t, e, n) {
        var l = be();
        if (n !== void 0) {
          var a = n(e);
          if (gl) {
            ve(!0);
            try {
              n(e);
            } finally {
              ve(!1);
            }
          }
        } else a = e;
        return (
          (l.memoizedState = l.baseState = a),
          (t = {
            pending: null,
            lanes: 0,
            dispatch: null,
            lastRenderedReducer: t,
            lastRenderedState: a,
          }),
          (l.queue = t),
          (t = t.dispatch = Vg.bind(null, gt, t)),
          [l.memoizedState, t]
        );
      },
      useRef: function (t) {
        var e = be();
        return ((t = { current: t }), (e.memoizedState = t));
      },
      useState: function (t) {
        t = nc(t);
        var e = t.queue,
          n = $s.bind(null, gt, e);
        return ((e.dispatch = n), [t.memoizedState, n]);
      },
      useDebugValue: ac,
      useDeferredValue: function (t, e) {
        var n = be();
        return uc(n, t, e);
      },
      useTransition: function () {
        var t = nc(!1);
        return (
          (t = Ks.bind(null, gt, t.queue, !0, !1)),
          (be().memoizedState = t),
          [!1, t]
        );
      },
      useSyncExternalStore: function (t, e, n) {
        var l = gt,
          a = be();
        if (Mt) {
          if (n === void 0) throw Error(c(407));
          n = n();
        } else {
          if (((n = e()), Xt === null)) throw Error(c(349));
          (Ot & 127) !== 0 || Es(l, e, n);
        }
        a.memoizedState = n;
        var o = { value: n, getSnapshot: e };
        return (
          (a.queue = o),
          Hs(Ts.bind(null, l, o, t), [t]),
          (l.flags |= 2048),
          Il(9, { destroy: void 0 }, zs.bind(null, l, o, n, e), null),
          n
        );
      },
      useId: function () {
        var t = be(),
          e = Xt.identifierPrefix;
        if (Mt) {
          var n = nn,
            l = en;
          ((n = (l & ~(1 << (32 - Gt(l) - 1))).toString(32) + n),
            (e = "_" + e + "R_" + n),
            (n = Pa++),
            0 < n && (e += "H" + n.toString(32)),
            (e += "_"));
        } else ((n = Hg++), (e = "_" + e + "r_" + n.toString(32) + "_"));
        return (t.memoizedState = e);
      },
      useHostTransitionStatus: cc,
      useFormState: Ns,
      useActionState: Ns,
      useOptimistic: function (t) {
        var e = be();
        e.memoizedState = e.baseState = t;
        var n = {
          pending: null,
          lanes: 0,
          dispatch: null,
          lastRenderedReducer: null,
          lastRenderedState: null,
        };
        return (
          (e.queue = n),
          (e = oc.bind(null, gt, !0, n)),
          (n.dispatch = e),
          [t, e]
        );
      },
      useMemoCache: Pr,
      useCacheRefresh: function () {
        return (be().memoizedState = Qg.bind(null, gt));
      },
      useEffectEvent: function (t) {
        var e = be(),
          n = { impl: t };
        return (
          (e.memoizedState = n),
          function () {
            if ((Rt & 2) !== 0) throw Error(c(440));
            return n.impl.apply(void 0, arguments);
          }
        );
      },
    },
    fc = {
      readContext: fe,
      use: eu,
      useCallback: Qs,
      useContext: fe,
      useEffect: ic,
      useImperativeHandle: Xs,
      useInsertionEffect: qs,
      useLayoutEffect: Ys,
      useMemo: Vs,
      useReducer: nu,
      useRef: js,
      useState: function () {
        return nu(vn);
      },
      useDebugValue: ac,
      useDeferredValue: function (t, e) {
        var n = $t();
        return Zs(n, Lt.memoizedState, t, e);
      },
      useTransition: function () {
        var t = nu(vn)[0],
          e = $t().memoizedState;
        return [typeof t == "boolean" ? t : qi(t), e];
      },
      useSyncExternalStore: xs,
      useId: Is,
      useHostTransitionStatus: cc,
      useFormState: Rs,
      useActionState: Rs,
      useOptimistic: function (t, e) {
        var n = $t();
        return _s(n, Lt, t, e);
      },
      useMemoCache: Pr,
      useCacheRefresh: Ws,
    };
  fc.useEffectEvent = Ls;
  var nh = {
    readContext: fe,
    use: eu,
    useCallback: Qs,
    useContext: fe,
    useEffect: ic,
    useImperativeHandle: Xs,
    useInsertionEffect: qs,
    useLayoutEffect: Ys,
    useMemo: Vs,
    useReducer: ec,
    useRef: js,
    useState: function () {
      return ec(vn);
    },
    useDebugValue: ac,
    useDeferredValue: function (t, e) {
      var n = $t();
      return Lt === null ? uc(n, t, e) : Zs(n, Lt.memoizedState, t, e);
    },
    useTransition: function () {
      var t = ec(vn)[0],
        e = $t().memoizedState;
      return [typeof t == "boolean" ? t : qi(t), e];
    },
    useSyncExternalStore: xs,
    useId: Is,
    useHostTransitionStatus: cc,
    useFormState: Bs,
    useActionState: Bs,
    useOptimistic: function (t, e) {
      var n = $t();
      return Lt !== null
        ? _s(n, Lt, t, e)
        : ((n.baseState = t), [t, n.queue.dispatch]);
    },
    useMemoCache: Pr,
    useCacheRefresh: Ws,
  };
  nh.useEffectEvent = Ls;
  function sc(t, e, n, l) {
    ((e = t.memoizedState),
      (n = n(l, e)),
      (n = n == null ? e : v({}, e, n)),
      (t.memoizedState = n),
      t.lanes === 0 && (t.updateQueue.baseState = n));
  }
  var hc = {
    enqueueSetState: function (t, e, n) {
      t = t._reactInternals;
      var l = je(),
        a = jn(l);
      ((a.payload = e),
        n != null && (a.callback = n),
        (e = Hn(t, a, l)),
        e !== null && (Ce(e, t, l), Bi(e, t, l)));
    },
    enqueueReplaceState: function (t, e, n) {
      t = t._reactInternals;
      var l = je(),
        a = jn(l);
      ((a.tag = 1),
        (a.payload = e),
        n != null && (a.callback = n),
        (e = Hn(t, a, l)),
        e !== null && (Ce(e, t, l), Bi(e, t, l)));
    },
    enqueueForceUpdate: function (t, e) {
      t = t._reactInternals;
      var n = je(),
        l = jn(n);
      ((l.tag = 2),
        e != null && (l.callback = e),
        (e = Hn(t, l, n)),
        e !== null && (Ce(e, t, n), Bi(e, t, n)));
    },
  };
  function lh(t, e, n, l, a, o, h) {
    return (
      (t = t.stateNode),
      typeof t.shouldComponentUpdate == "function"
        ? t.shouldComponentUpdate(l, o, h)
        : e.prototype && e.prototype.isPureReactComponent
          ? !Oi(n, l) || !Oi(a, o)
          : !0
    );
  }
  function ih(t, e, n, l) {
    ((t = e.state),
      typeof e.componentWillReceiveProps == "function" &&
        e.componentWillReceiveProps(n, l),
      typeof e.UNSAFE_componentWillReceiveProps == "function" &&
        e.UNSAFE_componentWillReceiveProps(n, l),
      e.state !== t && hc.enqueueReplaceState(e, e.state, null));
  }
  function yl(t, e) {
    var n = e;
    if ("ref" in e) {
      n = {};
      for (var l in e) l !== "ref" && (n[l] = e[l]);
    }
    if ((t = t.defaultProps)) {
      n === e && (n = v({}, n));
      for (var a in t) n[a] === void 0 && (n[a] = t[a]);
    }
    return n;
  }
  function ah(t) {
    ja(t);
  }
  function uh(t) {
    console.error(t);
  }
  function rh(t) {
    ja(t);
  }
  function uu(t, e) {
    try {
      var n = t.onUncaughtError;
      n(e.value, { componentStack: e.stack });
    } catch (l) {
      setTimeout(function () {
        throw l;
      });
    }
  }
  function ch(t, e, n) {
    try {
      var l = t.onCaughtError;
      l(n.value, {
        componentStack: n.stack,
        errorBoundary: e.tag === 1 ? e.stateNode : null,
      });
    } catch (a) {
      setTimeout(function () {
        throw a;
      });
    }
  }
  function dc(t, e, n) {
    return (
      (n = jn(n)),
      (n.tag = 3),
      (n.payload = { element: null }),
      (n.callback = function () {
        uu(t, e);
      }),
      n
    );
  }
  function oh(t) {
    return ((t = jn(t)), (t.tag = 3), t);
  }
  function fh(t, e, n, l) {
    var a = n.type.getDerivedStateFromError;
    if (typeof a == "function") {
      var o = l.value;
      ((t.payload = function () {
        return a(o);
      }),
        (t.callback = function () {
          ch(e, n, l);
        }));
    }
    var h = n.stateNode;
    h !== null &&
      typeof h.componentDidCatch == "function" &&
      (t.callback = function () {
        (ch(e, n, l),
          typeof a != "function" &&
            (Qn === null ? (Qn = new Set([this])) : Qn.add(this)));
        var g = l.stack;
        this.componentDidCatch(l.value, {
          componentStack: g !== null ? g : "",
        });
      });
  }
  function Zg(t, e, n, l, a) {
    if (
      ((n.flags |= 32768),
      l !== null && typeof l == "object" && typeof l.then == "function")
    ) {
      if (
        ((e = n.alternate),
        e !== null && Gl(e, n, a, !0),
        (n = Ne.current),
        n !== null)
      ) {
        switch (n.tag) {
          case 31:
          case 13:
            return (
              Ke === null ? bu() : n.alternate === null && It === 0 && (It = 3),
              (n.flags &= -257),
              (n.flags |= 65536),
              (n.lanes = a),
              l === Ka
                ? (n.flags |= 16384)
                : ((e = n.updateQueue),
                  e === null ? (n.updateQueue = new Set([l])) : e.add(l),
                  Hc(t, l, a)),
              !1
            );
          case 22:
            return (
              (n.flags |= 65536),
              l === Ka
                ? (n.flags |= 16384)
                : ((e = n.updateQueue),
                  e === null
                    ? ((e = {
                        transitions: null,
                        markerInstances: null,
                        retryQueue: new Set([l]),
                      }),
                      (n.updateQueue = e))
                    : ((n = e.retryQueue),
                      n === null ? (e.retryQueue = new Set([l])) : n.add(l)),
                  Hc(t, l, a)),
              !1
            );
        }
        throw Error(c(435, n.tag));
      }
      return (Hc(t, l, a), bu(), !1);
    }
    if (Mt)
      return (
        (e = Ne.current),
        e !== null
          ? ((e.flags & 65536) === 0 && (e.flags |= 256),
            (e.flags |= 65536),
            (e.lanes = a),
            l !== wr && ((t = Error(c(422), { cause: l })), ki(Xe(t, n))))
          : (l !== wr && ((e = Error(c(423), { cause: l })), ki(Xe(e, n))),
            (t = t.current.alternate),
            (t.flags |= 65536),
            (a &= -a),
            (t.lanes |= a),
            (l = Xe(l, n)),
            (a = dc(t.stateNode, l, a)),
            Xr(t, a),
            It !== 4 && (It = 2)),
        !1
      );
    var o = Error(c(520), { cause: l });
    if (
      ((o = Xe(o, n)),
      Ii === null ? (Ii = [o]) : Ii.push(o),
      It !== 4 && (It = 2),
      e === null)
    )
      return !0;
    ((l = Xe(l, n)), (n = e));
    do {
      switch (n.tag) {
        case 3:
          return (
            (n.flags |= 65536),
            (t = a & -a),
            (n.lanes |= t),
            (t = dc(n.stateNode, l, t)),
            Xr(n, t),
            !1
          );
        case 1:
          if (
            ((e = n.type),
            (o = n.stateNode),
            (n.flags & 128) === 0 &&
              (typeof e.getDerivedStateFromError == "function" ||
                (o !== null &&
                  typeof o.componentDidCatch == "function" &&
                  (Qn === null || !Qn.has(o)))))
          )
            return (
              (n.flags |= 65536),
              (a &= -a),
              (n.lanes |= a),
              (a = oh(a)),
              fh(a, t, n, l),
              Xr(n, a),
              !1
            );
      }
      n = n.return;
    } while (n !== null);
    return !1;
  }
  var pc = Error(c(461)),
    ee = !1;
  function se(t, e, n, l) {
    e.child = t === null ? ps(e, null, n, l) : ml(e, t.child, n, l);
  }
  function sh(t, e, n, l, a) {
    n = n.render;
    var o = e.ref;
    if ("ref" in l) {
      var h = {};
      for (var g in l) g !== "ref" && (h[g] = l[g]);
    } else h = l;
    return (
      sl(e),
      (l = Fr(t, e, n, h, o, a)),
      (g = Ir()),
      t !== null && !ee
        ? (Wr(t, e, a), Sn(t, e, a))
        : (Mt && g && Mr(e), (e.flags |= 1), se(t, e, l, a), e.child)
    );
  }
  function hh(t, e, n, l, a) {
    if (t === null) {
      var o = n.type;
      return typeof o == "function" &&
        !_r(o) &&
        o.defaultProps === void 0 &&
        n.compare === null
        ? ((e.tag = 15), (e.type = o), dh(t, e, o, l, a))
        : ((t = Ya(n.type, null, l, e, e.mode, a)),
          (t.ref = e.ref),
          (t.return = e),
          (e.child = t));
    }
    if (((o = t.child), !Ec(t, a))) {
      var h = o.memoizedProps;
      if (
        ((n = n.compare), (n = n !== null ? n : Oi), n(h, l) && t.ref === e.ref)
      )
        return Sn(t, e, a);
    }
    return (
      (e.flags |= 1),
      (t = pn(o, l)),
      (t.ref = e.ref),
      (t.return = e),
      (e.child = t)
    );
  }
  function dh(t, e, n, l, a) {
    if (t !== null) {
      var o = t.memoizedProps;
      if (Oi(o, l) && t.ref === e.ref)
        if (((ee = !1), (e.pendingProps = l = o), Ec(t, a)))
          (t.flags & 131072) !== 0 && (ee = !0);
        else return ((e.lanes = t.lanes), Sn(t, e, a));
    }
    return mc(t, e, n, l, a);
  }
  function ph(t, e, n, l) {
    var a = l.children,
      o = t !== null ? t.memoizedState : null;
    if (
      (t === null &&
        e.stateNode === null &&
        (e.stateNode = {
          _visibility: 1,
          _pendingMarkers: null,
          _retryCache: null,
          _transitions: null,
        }),
      l.mode === "hidden")
    ) {
      if ((e.flags & 128) !== 0) {
        if (((o = o !== null ? o.baseLanes | n : n), t !== null)) {
          for (l = e.child = t.child, a = 0; l !== null; )
            ((a = a | l.lanes | l.childLanes), (l = l.sibling));
          l = a & ~o;
        } else ((l = 0), (e.child = null));
        return mh(t, e, o, n, l);
      }
      if ((n & 536870912) !== 0)
        ((e.memoizedState = { baseLanes: 0, cachePool: null }),
          t !== null && Va(e, o !== null ? o.cachePool : null),
          o !== null ? ys(e, o) : Vr(),
          bs(e));
      else
        return (
          (l = e.lanes = 536870912),
          mh(t, e, o !== null ? o.baseLanes | n : n, n, l)
        );
    } else
      o !== null
        ? (Va(e, o.cachePool), ys(e, o), qn(), (e.memoizedState = null))
        : (t !== null && Va(e, null), Vr(), qn());
    return (se(t, e, a, n), e.child);
  }
  function Xi(t, e) {
    return (
      (t !== null && t.tag === 22) ||
        e.stateNode !== null ||
        (e.stateNode = {
          _visibility: 1,
          _pendingMarkers: null,
          _retryCache: null,
          _transitions: null,
        }),
      e.sibling
    );
  }
  function mh(t, e, n, l, a) {
    var o = Lr();
    return (
      (o = o === null ? null : { parent: Pt._currentValue, pool: o }),
      (e.memoizedState = { baseLanes: n, cachePool: o }),
      t !== null && Va(e, null),
      Vr(),
      bs(e),
      t !== null && Gl(t, e, l, !0),
      (e.childLanes = a),
      null
    );
  }
  function ru(t, e) {
    return (
      (e = ou({ mode: e.mode, children: e.children }, t.mode)),
      (e.ref = t.ref),
      (t.child = e),
      (e.return = t),
      e
    );
  }
  function gh(t, e, n) {
    return (
      ml(e, t.child, null, n),
      (t = ru(e, e.pendingProps)),
      (t.flags |= 2),
      Re(e),
      (e.memoizedState = null),
      t
    );
  }
  function Kg(t, e, n) {
    var l = e.pendingProps,
      a = (e.flags & 128) !== 0;
    if (((e.flags &= -129), t === null)) {
      if (Mt) {
        if (l.mode === "hidden")
          return ((t = ru(e, l)), (e.lanes = 536870912), Xi(null, t));
        if (
          (Kr(e),
          (t = Zt)
            ? ((t = Od(t, Ze)),
              (t = t !== null && t.data === "&" ? t : null),
              t !== null &&
                ((e.memoizedState = {
                  dehydrated: t,
                  treeContext: wn !== null ? { id: en, overflow: nn } : null,
                  retryLane: 536870912,
                  hydrationErrors: null,
                }),
                (n = Pf(t)),
                (n.return = e),
                (e.child = n),
                (oe = e),
                (Zt = null)))
            : (t = null),
          t === null)
        )
          throw Rn(e);
        return ((e.lanes = 536870912), null);
      }
      return ru(e, l);
    }
    var o = t.memoizedState;
    if (o !== null) {
      var h = o.dehydrated;
      if ((Kr(e), a))
        if (e.flags & 256) ((e.flags &= -257), (e = gh(t, e, n)));
        else if (e.memoizedState !== null)
          ((e.child = t.child), (e.flags |= 128), (e = null));
        else throw Error(c(558));
      else if (
        (ee || Gl(t, e, n, !1), (a = (n & t.childLanes) !== 0), ee || a)
      ) {
        if (
          ((l = Xt),
          l !== null && ((h = uf(l, n)), h !== 0 && h !== o.retryLane))
        )
          throw ((o.retryLane = h), rl(t, h), Ce(l, t, h), pc);
        (bu(), (e = gh(t, e, n)));
      } else
        ((t = o.treeContext),
          (Zt = Je(h.nextSibling)),
          (oe = e),
          (Mt = !0),
          (Nn = null),
          (Ze = !1),
          t !== null && ns(e, t),
          (e = ru(e, l)),
          (e.flags |= 4096));
      return e;
    }
    return (
      (t = pn(t.child, { mode: l.mode, children: l.children })),
      (t.ref = e.ref),
      (e.child = t),
      (t.return = e),
      t
    );
  }
  function cu(t, e) {
    var n = e.ref;
    if (n === null) t !== null && t.ref !== null && (e.flags |= 4194816);
    else {
      if (typeof n != "function" && typeof n != "object") throw Error(c(284));
      (t === null || t.ref !== n) && (e.flags |= 4194816);
    }
  }
  function mc(t, e, n, l, a) {
    return (
      sl(e),
      (n = Fr(t, e, n, l, void 0, a)),
      (l = Ir()),
      t !== null && !ee
        ? (Wr(t, e, a), Sn(t, e, a))
        : (Mt && l && Mr(e), (e.flags |= 1), se(t, e, n, a), e.child)
    );
  }
  function yh(t, e, n, l, a, o) {
    return (
      sl(e),
      (e.updateQueue = null),
      (n = Ss(e, l, n, a)),
      vs(t),
      (l = Ir()),
      t !== null && !ee
        ? (Wr(t, e, o), Sn(t, e, o))
        : (Mt && l && Mr(e), (e.flags |= 1), se(t, e, n, o), e.child)
    );
  }
  function bh(t, e, n, l, a) {
    if ((sl(e), e.stateNode === null)) {
      var o = Hl,
        h = n.contextType;
      (typeof h == "object" && h !== null && (o = fe(h)),
        (o = new n(l, o)),
        (e.memoizedState =
          o.state !== null && o.state !== void 0 ? o.state : null),
        (o.updater = hc),
        (e.stateNode = o),
        (o._reactInternals = e),
        (o = e.stateNode),
        (o.props = l),
        (o.state = e.memoizedState),
        (o.refs = {}),
        Yr(e),
        (h = n.contextType),
        (o.context = typeof h == "object" && h !== null ? fe(h) : Hl),
        (o.state = e.memoizedState),
        (h = n.getDerivedStateFromProps),
        typeof h == "function" && (sc(e, n, h, l), (o.state = e.memoizedState)),
        typeof n.getDerivedStateFromProps == "function" ||
          typeof o.getSnapshotBeforeUpdate == "function" ||
          (typeof o.UNSAFE_componentWillMount != "function" &&
            typeof o.componentWillMount != "function") ||
          ((h = o.state),
          typeof o.componentWillMount == "function" && o.componentWillMount(),
          typeof o.UNSAFE_componentWillMount == "function" &&
            o.UNSAFE_componentWillMount(),
          h !== o.state && hc.enqueueReplaceState(o, o.state, null),
          Hi(e, l, o, a),
          ji(),
          (o.state = e.memoizedState)),
        typeof o.componentDidMount == "function" && (e.flags |= 4194308),
        (l = !0));
    } else if (t === null) {
      o = e.stateNode;
      var g = e.memoizedProps,
        z = yl(n, g);
      o.props = z;
      var D = o.context,
        N = n.contextType;
      ((h = Hl), typeof N == "object" && N !== null && (h = fe(N)));
      var q = n.getDerivedStateFromProps;
      ((N =
        typeof q == "function" ||
        typeof o.getSnapshotBeforeUpdate == "function"),
        (g = e.pendingProps !== g),
        N ||
          (typeof o.UNSAFE_componentWillReceiveProps != "function" &&
            typeof o.componentWillReceiveProps != "function") ||
          ((g || D !== h) && ih(e, o, l, h)),
        (Bn = !1));
      var k = e.memoizedState;
      ((o.state = k),
        Hi(e, l, o, a),
        ji(),
        (D = e.memoizedState),
        g || k !== D || Bn
          ? (typeof q == "function" && (sc(e, n, q, l), (D = e.memoizedState)),
            (z = Bn || lh(e, n, z, l, k, D, h))
              ? (N ||
                  (typeof o.UNSAFE_componentWillMount != "function" &&
                    typeof o.componentWillMount != "function") ||
                  (typeof o.componentWillMount == "function" &&
                    o.componentWillMount(),
                  typeof o.UNSAFE_componentWillMount == "function" &&
                    o.UNSAFE_componentWillMount()),
                typeof o.componentDidMount == "function" &&
                  (e.flags |= 4194308))
              : (typeof o.componentDidMount == "function" &&
                  (e.flags |= 4194308),
                (e.memoizedProps = l),
                (e.memoizedState = D)),
            (o.props = l),
            (o.state = D),
            (o.context = h),
            (l = z))
          : (typeof o.componentDidMount == "function" && (e.flags |= 4194308),
            (l = !1)));
    } else {
      ((o = e.stateNode),
        Gr(t, e),
        (h = e.memoizedProps),
        (N = yl(n, h)),
        (o.props = N),
        (q = e.pendingProps),
        (k = o.context),
        (D = n.contextType),
        (z = Hl),
        typeof D == "object" && D !== null && (z = fe(D)),
        (g = n.getDerivedStateFromProps),
        (D =
          typeof g == "function" ||
          typeof o.getSnapshotBeforeUpdate == "function") ||
          (typeof o.UNSAFE_componentWillReceiveProps != "function" &&
            typeof o.componentWillReceiveProps != "function") ||
          ((h !== q || k !== z) && ih(e, o, l, z)),
        (Bn = !1),
        (k = e.memoizedState),
        (o.state = k),
        Hi(e, l, o, a),
        ji());
      var w = e.memoizedState;
      h !== q ||
      k !== w ||
      Bn ||
      (t !== null && t.dependencies !== null && Xa(t.dependencies))
        ? (typeof g == "function" && (sc(e, n, g, l), (w = e.memoizedState)),
          (N =
            Bn ||
            lh(e, n, N, l, k, w, z) ||
            (t !== null && t.dependencies !== null && Xa(t.dependencies)))
            ? (D ||
                (typeof o.UNSAFE_componentWillUpdate != "function" &&
                  typeof o.componentWillUpdate != "function") ||
                (typeof o.componentWillUpdate == "function" &&
                  o.componentWillUpdate(l, w, z),
                typeof o.UNSAFE_componentWillUpdate == "function" &&
                  o.UNSAFE_componentWillUpdate(l, w, z)),
              typeof o.componentDidUpdate == "function" && (e.flags |= 4),
              typeof o.getSnapshotBeforeUpdate == "function" &&
                (e.flags |= 1024))
            : (typeof o.componentDidUpdate != "function" ||
                (h === t.memoizedProps && k === t.memoizedState) ||
                (e.flags |= 4),
              typeof o.getSnapshotBeforeUpdate != "function" ||
                (h === t.memoizedProps && k === t.memoizedState) ||
                (e.flags |= 1024),
              (e.memoizedProps = l),
              (e.memoizedState = w)),
          (o.props = l),
          (o.state = w),
          (o.context = z),
          (l = N))
        : (typeof o.componentDidUpdate != "function" ||
            (h === t.memoizedProps && k === t.memoizedState) ||
            (e.flags |= 4),
          typeof o.getSnapshotBeforeUpdate != "function" ||
            (h === t.memoizedProps && k === t.memoizedState) ||
            (e.flags |= 1024),
          (l = !1));
    }
    return (
      (o = l),
      cu(t, e),
      (l = (e.flags & 128) !== 0),
      o || l
        ? ((o = e.stateNode),
          (n =
            l && typeof n.getDerivedStateFromError != "function"
              ? null
              : o.render()),
          (e.flags |= 1),
          t !== null && l
            ? ((e.child = ml(e, t.child, null, a)),
              (e.child = ml(e, null, n, a)))
            : se(t, e, n, a),
          (e.memoizedState = o.state),
          (t = e.child))
        : (t = Sn(t, e, a)),
      t
    );
  }
  function vh(t, e, n, l) {
    return (ol(), (e.flags |= 256), se(t, e, n, l), e.child);
  }
  var gc = {
    dehydrated: null,
    treeContext: null,
    retryLane: 0,
    hydrationErrors: null,
  };
  function yc(t) {
    return { baseLanes: t, cachePool: cs() };
  }
  function bc(t, e, n) {
    return ((t = t !== null ? t.childLanes & ~n : 0), e && (t |= Be), t);
  }
  function Sh(t, e, n) {
    var l = e.pendingProps,
      a = !1,
      o = (e.flags & 128) !== 0,
      h;
    if (
      ((h = o) ||
        (h =
          t !== null && t.memoizedState === null ? !1 : (Wt.current & 2) !== 0),
      h && ((a = !0), (e.flags &= -129)),
      (h = (e.flags & 32) !== 0),
      (e.flags &= -33),
      t === null)
    ) {
      if (Mt) {
        if (
          (a ? Ln(e) : qn(),
          (t = Zt)
            ? ((t = Od(t, Ze)),
              (t = t !== null && t.data !== "&" ? t : null),
              t !== null &&
                ((e.memoizedState = {
                  dehydrated: t,
                  treeContext: wn !== null ? { id: en, overflow: nn } : null,
                  retryLane: 536870912,
                  hydrationErrors: null,
                }),
                (n = Pf(t)),
                (n.return = e),
                (e.child = n),
                (oe = e),
                (Zt = null)))
            : (t = null),
          t === null)
        )
          throw Rn(e);
        return (to(t) ? (e.lanes = 32) : (e.lanes = 536870912), null);
      }
      var g = l.children;
      return (
        (l = l.fallback),
        a
          ? (qn(),
            (a = e.mode),
            (g = ou({ mode: "hidden", children: g }, a)),
            (l = cl(l, a, n, null)),
            (g.return = e),
            (l.return = e),
            (g.sibling = l),
            (e.child = g),
            (l = e.child),
            (l.memoizedState = yc(n)),
            (l.childLanes = bc(t, h, n)),
            (e.memoizedState = gc),
            Xi(null, l))
          : (Ln(e), vc(e, g))
      );
    }
    var z = t.memoizedState;
    if (z !== null && ((g = z.dehydrated), g !== null)) {
      if (o)
        e.flags & 256
          ? (Ln(e), (e.flags &= -257), (e = Sc(t, e, n)))
          : e.memoizedState !== null
            ? (qn(), (e.child = t.child), (e.flags |= 128), (e = null))
            : (qn(),
              (g = l.fallback),
              (a = e.mode),
              (l = ou({ mode: "visible", children: l.children }, a)),
              (g = cl(g, a, n, null)),
              (g.flags |= 2),
              (l.return = e),
              (g.return = e),
              (l.sibling = g),
              (e.child = l),
              ml(e, t.child, null, n),
              (l = e.child),
              (l.memoizedState = yc(n)),
              (l.childLanes = bc(t, h, n)),
              (e.memoizedState = gc),
              (e = Xi(null, l)));
      else if ((Ln(e), to(g))) {
        if (((h = g.nextSibling && g.nextSibling.dataset), h)) var D = h.dgst;
        ((h = D),
          (l = Error(c(419))),
          (l.stack = ""),
          (l.digest = h),
          ki({ value: l, source: null, stack: null }),
          (e = Sc(t, e, n)));
      } else if (
        (ee || Gl(t, e, n, !1), (h = (n & t.childLanes) !== 0), ee || h)
      ) {
        if (
          ((h = Xt),
          h !== null && ((l = uf(h, n)), l !== 0 && l !== z.retryLane))
        )
          throw ((z.retryLane = l), rl(t, l), Ce(h, t, l), pc);
        (Pc(g) || bu(), (e = Sc(t, e, n)));
      } else
        Pc(g)
          ? ((e.flags |= 192), (e.child = t.child), (e = null))
          : ((t = z.treeContext),
            (Zt = Je(g.nextSibling)),
            (oe = e),
            (Mt = !0),
            (Nn = null),
            (Ze = !1),
            t !== null && ns(e, t),
            (e = vc(e, l.children)),
            (e.flags |= 4096));
      return e;
    }
    return a
      ? (qn(),
        (g = l.fallback),
        (a = e.mode),
        (z = t.child),
        (D = z.sibling),
        (l = pn(z, { mode: "hidden", children: l.children })),
        (l.subtreeFlags = z.subtreeFlags & 65011712),
        D !== null ? (g = pn(D, g)) : ((g = cl(g, a, n, null)), (g.flags |= 2)),
        (g.return = e),
        (l.return = e),
        (l.sibling = g),
        (e.child = l),
        Xi(null, l),
        (l = e.child),
        (g = t.child.memoizedState),
        g === null
          ? (g = yc(n))
          : ((a = g.cachePool),
            a !== null
              ? ((z = Pt._currentValue),
                (a = a.parent !== z ? { parent: z, pool: z } : a))
              : (a = cs()),
            (g = { baseLanes: g.baseLanes | n, cachePool: a })),
        (l.memoizedState = g),
        (l.childLanes = bc(t, h, n)),
        (e.memoizedState = gc),
        Xi(t.child, l))
      : (Ln(e),
        (n = t.child),
        (t = n.sibling),
        (n = pn(n, { mode: "visible", children: l.children })),
        (n.return = e),
        (n.sibling = null),
        t !== null &&
          ((h = e.deletions),
          h === null ? ((e.deletions = [t]), (e.flags |= 16)) : h.push(t)),
        (e.child = n),
        (e.memoizedState = null),
        n);
  }
  function vc(t, e) {
    return (
      (e = ou({ mode: "visible", children: e }, t.mode)),
      (e.return = t),
      (t.child = e)
    );
  }
  function ou(t, e) {
    return ((t = we(22, t, null, e)), (t.lanes = 0), t);
  }
  function Sc(t, e, n) {
    return (
      ml(e, t.child, null, n),
      (t = vc(e, e.pendingProps.children)),
      (t.flags |= 2),
      (e.memoizedState = null),
      t
    );
  }
  function xh(t, e, n) {
    t.lanes |= e;
    var l = t.alternate;
    (l !== null && (l.lanes |= e), Ur(t.return, e, n));
  }
  function xc(t, e, n, l, a, o) {
    var h = t.memoizedState;
    h === null
      ? (t.memoizedState = {
          isBackwards: e,
          rendering: null,
          renderingStartTime: 0,
          last: l,
          tail: n,
          tailMode: a,
          treeForkCount: o,
        })
      : ((h.isBackwards = e),
        (h.rendering = null),
        (h.renderingStartTime = 0),
        (h.last = l),
        (h.tail = n),
        (h.tailMode = a),
        (h.treeForkCount = o));
  }
  function Eh(t, e, n) {
    var l = e.pendingProps,
      a = l.revealOrder,
      o = l.tail;
    l = l.children;
    var h = Wt.current,
      g = (h & 2) !== 0;
    if (
      (g ? ((h = (h & 1) | 2), (e.flags |= 128)) : (h &= 1),
      S(Wt, h),
      se(t, e, l, n),
      (l = Mt ? Mi : 0),
      !g && t !== null && (t.flags & 128) !== 0)
    )
      t: for (t = e.child; t !== null; ) {
        if (t.tag === 13) t.memoizedState !== null && xh(t, n, e);
        else if (t.tag === 19) xh(t, n, e);
        else if (t.child !== null) {
          ((t.child.return = t), (t = t.child));
          continue;
        }
        if (t === e) break t;
        for (; t.sibling === null; ) {
          if (t.return === null || t.return === e) break t;
          t = t.return;
        }
        ((t.sibling.return = t.return), (t = t.sibling));
      }
    switch (a) {
      case "forwards":
        for (n = e.child, a = null; n !== null; )
          ((t = n.alternate),
            t !== null && Wa(t) === null && (a = n),
            (n = n.sibling));
        ((n = a),
          n === null
            ? ((a = e.child), (e.child = null))
            : ((a = n.sibling), (n.sibling = null)),
          xc(e, !1, a, n, o, l));
        break;
      case "backwards":
      case "unstable_legacy-backwards":
        for (n = null, a = e.child, e.child = null; a !== null; ) {
          if (((t = a.alternate), t !== null && Wa(t) === null)) {
            e.child = a;
            break;
          }
          ((t = a.sibling), (a.sibling = n), (n = a), (a = t));
        }
        xc(e, !0, n, null, o, l);
        break;
      case "together":
        xc(e, !1, null, null, void 0, l);
        break;
      default:
        e.memoizedState = null;
    }
    return e.child;
  }
  function Sn(t, e, n) {
    if (
      (t !== null && (e.dependencies = t.dependencies),
      (Xn |= e.lanes),
      (n & e.childLanes) === 0)
    )
      if (t !== null) {
        if ((Gl(t, e, n, !1), (n & e.childLanes) === 0)) return null;
      } else return null;
    if (t !== null && e.child !== t.child) throw Error(c(153));
    if (e.child !== null) {
      for (
        t = e.child, n = pn(t, t.pendingProps), e.child = n, n.return = e;
        t.sibling !== null;
      )
        ((t = t.sibling),
          (n = n.sibling = pn(t, t.pendingProps)),
          (n.return = e));
      n.sibling = null;
    }
    return e.child;
  }
  function Ec(t, e) {
    return (t.lanes & e) !== 0
      ? !0
      : ((t = t.dependencies), !!(t !== null && Xa(t)));
  }
  function Jg(t, e, n) {
    switch (e.tag) {
      case 3:
        (V(e, e.stateNode.containerInfo),
          Un(e, Pt, t.memoizedState.cache),
          ol());
        break;
      case 27:
      case 5:
        kt(e);
        break;
      case 4:
        V(e, e.stateNode.containerInfo);
        break;
      case 10:
        Un(e, e.type, e.memoizedProps.value);
        break;
      case 31:
        if (e.memoizedState !== null) return ((e.flags |= 128), Kr(e), null);
        break;
      case 13:
        var l = e.memoizedState;
        if (l !== null)
          return l.dehydrated !== null
            ? (Ln(e), (e.flags |= 128), null)
            : (n & e.child.childLanes) !== 0
              ? Sh(t, e, n)
              : (Ln(e), (t = Sn(t, e, n)), t !== null ? t.sibling : null);
        Ln(e);
        break;
      case 19:
        var a = (t.flags & 128) !== 0;
        if (
          ((l = (n & e.childLanes) !== 0),
          l || (Gl(t, e, n, !1), (l = (n & e.childLanes) !== 0)),
          a)
        ) {
          if (l) return Eh(t, e, n);
          e.flags |= 128;
        }
        if (
          ((a = e.memoizedState),
          a !== null &&
            ((a.rendering = null), (a.tail = null), (a.lastEffect = null)),
          S(Wt, Wt.current),
          l)
        )
          break;
        return null;
      case 22:
        return ((e.lanes = 0), ph(t, e, n, e.pendingProps));
      case 24:
        Un(e, Pt, t.memoizedState.cache);
    }
    return Sn(t, e, n);
  }
  function zh(t, e, n) {
    if (t !== null)
      if (t.memoizedProps !== e.pendingProps) ee = !0;
      else {
        if (!Ec(t, n) && (e.flags & 128) === 0) return ((ee = !1), Jg(t, e, n));
        ee = (t.flags & 131072) !== 0;
      }
    else ((ee = !1), Mt && (e.flags & 1048576) !== 0 && es(e, Mi, e.index));
    switch (((e.lanes = 0), e.tag)) {
      case 16:
        t: {
          var l = e.pendingProps;
          if (((t = dl(e.elementType)), (e.type = t), typeof t == "function"))
            _r(t)
              ? ((l = yl(t, l)), (e.tag = 1), (e = bh(null, e, t, l, n)))
              : ((e.tag = 0), (e = mc(null, e, t, l, n)));
          else {
            if (t != null) {
              var a = t.$$typeof;
              if (a === mt) {
                ((e.tag = 11), (e = sh(null, e, t, l, n)));
                break t;
              } else if (a === W) {
                ((e.tag = 14), (e = hh(null, e, t, l, n)));
                break t;
              }
            }
            throw ((e = lt(t) || t), Error(c(306, e, "")));
          }
        }
        return e;
      case 0:
        return mc(t, e, e.type, e.pendingProps, n);
      case 1:
        return ((l = e.type), (a = yl(l, e.pendingProps)), bh(t, e, l, a, n));
      case 3:
        t: {
          if ((V(e, e.stateNode.containerInfo), t === null))
            throw Error(c(387));
          l = e.pendingProps;
          var o = e.memoizedState;
          ((a = o.element), Gr(t, e), Hi(e, l, null, n));
          var h = e.memoizedState;
          if (
            ((l = h.cache),
            Un(e, Pt, l),
            l !== o.cache && Br(e, [Pt], n, !0),
            ji(),
            (l = h.element),
            o.isDehydrated)
          )
            if (
              ((o = { element: l, isDehydrated: !1, cache: h.cache }),
              (e.updateQueue.baseState = o),
              (e.memoizedState = o),
              e.flags & 256)
            ) {
              e = vh(t, e, l, n);
              break t;
            } else if (l !== a) {
              ((a = Xe(Error(c(424)), e)), ki(a), (e = vh(t, e, l, n)));
              break t;
            } else
              for (
                t = e.stateNode.containerInfo,
                  t.nodeType === 9
                    ? (t = t.body)
                    : (t = t.nodeName === "HTML" ? t.ownerDocument.body : t),
                  Zt = Je(t.firstChild),
                  oe = e,
                  Mt = !0,
                  Nn = null,
                  Ze = !0,
                  n = ps(e, null, l, n),
                  e.child = n;
                n;
              )
                ((n.flags = (n.flags & -3) | 4096), (n = n.sibling));
          else {
            if ((ol(), l === a)) {
              e = Sn(t, e, n);
              break t;
            }
            se(t, e, l, n);
          }
          e = e.child;
        }
        return e;
      case 26:
        return (
          cu(t, e),
          t === null
            ? (n = Rd(e.type, null, e.pendingProps, null))
              ? (e.memoizedState = n)
              : Mt ||
                ((n = e.type),
                (t = e.pendingProps),
                (l = Au(at.current).createElement(n)),
                (l[ce] = e),
                (l[Se] = t),
                he(l, n, t),
                ue(l),
                (e.stateNode = l))
            : (e.memoizedState = Rd(
                e.type,
                t.memoizedProps,
                e.pendingProps,
                t.memoizedState,
              )),
          null
        );
      case 27:
        return (
          kt(e),
          t === null &&
            Mt &&
            ((l = e.stateNode = kd(e.type, e.pendingProps, at.current)),
            (oe = e),
            (Ze = !0),
            (a = Zt),
            Jn(e.type) ? ((eo = a), (Zt = Je(l.firstChild))) : (Zt = a)),
          se(t, e, e.pendingProps.children, n),
          cu(t, e),
          t === null && (e.flags |= 4194304),
          e.child
        );
      case 5:
        return (
          t === null &&
            Mt &&
            ((a = l = Zt) &&
              ((l = Ty(l, e.type, e.pendingProps, Ze)),
              l !== null
                ? ((e.stateNode = l),
                  (oe = e),
                  (Zt = Je(l.firstChild)),
                  (Ze = !1),
                  (a = !0))
                : (a = !1)),
            a || Rn(e)),
          kt(e),
          (a = e.type),
          (o = e.pendingProps),
          (h = t !== null ? t.memoizedProps : null),
          (l = o.children),
          Ic(a, o) ? (l = null) : h !== null && Ic(a, h) && (e.flags |= 32),
          e.memoizedState !== null &&
            ((a = Fr(t, e, Lg, null, null, n)), (ia._currentValue = a)),
          cu(t, e),
          se(t, e, l, n),
          e.child
        );
      case 6:
        return (
          t === null &&
            Mt &&
            ((t = n = Zt) &&
              ((n = Ay(n, e.pendingProps, Ze)),
              n !== null
                ? ((e.stateNode = n), (oe = e), (Zt = null), (t = !0))
                : (t = !1)),
            t || Rn(e)),
          null
        );
      case 13:
        return Sh(t, e, n);
      case 4:
        return (
          V(e, e.stateNode.containerInfo),
          (l = e.pendingProps),
          t === null ? (e.child = ml(e, null, l, n)) : se(t, e, l, n),
          e.child
        );
      case 11:
        return sh(t, e, e.type, e.pendingProps, n);
      case 7:
        return (se(t, e, e.pendingProps, n), e.child);
      case 8:
        return (se(t, e, e.pendingProps.children, n), e.child);
      case 12:
        return (se(t, e, e.pendingProps.children, n), e.child);
      case 10:
        return (
          (l = e.pendingProps),
          Un(e, e.type, l.value),
          se(t, e, l.children, n),
          e.child
        );
      case 9:
        return (
          (a = e.type._context),
          (l = e.pendingProps.children),
          sl(e),
          (a = fe(a)),
          (l = l(a)),
          (e.flags |= 1),
          se(t, e, l, n),
          e.child
        );
      case 14:
        return hh(t, e, e.type, e.pendingProps, n);
      case 15:
        return dh(t, e, e.type, e.pendingProps, n);
      case 19:
        return Eh(t, e, n);
      case 31:
        return Kg(t, e, n);
      case 22:
        return ph(t, e, n, e.pendingProps);
      case 24:
        return (
          sl(e),
          (l = fe(Pt)),
          t === null
            ? ((a = Lr()),
              a === null &&
                ((a = Xt),
                (o = jr()),
                (a.pooledCache = o),
                o.refCount++,
                o !== null && (a.pooledCacheLanes |= n),
                (a = o)),
              (e.memoizedState = { parent: l, cache: a }),
              Yr(e),
              Un(e, Pt, a))
            : ((t.lanes & n) !== 0 && (Gr(t, e), Hi(e, null, null, n), ji()),
              (a = t.memoizedState),
              (o = e.memoizedState),
              a.parent !== l
                ? ((a = { parent: l, cache: l }),
                  (e.memoizedState = a),
                  e.lanes === 0 &&
                    (e.memoizedState = e.updateQueue.baseState = a),
                  Un(e, Pt, l))
                : ((l = o.cache),
                  Un(e, Pt, l),
                  l !== a.cache && Br(e, [Pt], n, !0))),
          se(t, e, e.pendingProps.children, n),
          e.child
        );
      case 29:
        throw e.pendingProps;
    }
    throw Error(c(156, e.tag));
  }
  function xn(t) {
    t.flags |= 4;
  }
  function zc(t, e, n, l, a) {
    if (((e = (t.mode & 32) !== 0) && (e = !1), e)) {
      if (((t.flags |= 16777216), (a & 335544128) === a))
        if (t.stateNode.complete) t.flags |= 8192;
        else if (Ih()) t.flags |= 8192;
        else throw ((pl = Ka), qr);
    } else t.flags &= -16777217;
  }
  function Th(t, e) {
    if (e.type !== "stylesheet" || (e.state.loading & 4) !== 0)
      t.flags &= -16777217;
    else if (((t.flags |= 16777216), !Ld(e)))
      if (Ih()) t.flags |= 8192;
      else throw ((pl = Ka), qr);
  }
  function fu(t, e) {
    (e !== null && (t.flags |= 4),
      t.flags & 16384 &&
        ((e = t.tag !== 22 ? nf() : 536870912), (t.lanes |= e), (ti |= e)));
  }
  function Qi(t, e) {
    if (!Mt)
      switch (t.tailMode) {
        case "hidden":
          e = t.tail;
          for (var n = null; e !== null; )
            (e.alternate !== null && (n = e), (e = e.sibling));
          n === null ? (t.tail = null) : (n.sibling = null);
          break;
        case "collapsed":
          n = t.tail;
          for (var l = null; n !== null; )
            (n.alternate !== null && (l = n), (n = n.sibling));
          l === null
            ? e || t.tail === null
              ? (t.tail = null)
              : (t.tail.sibling = null)
            : (l.sibling = null);
      }
  }
  function Kt(t) {
    var e = t.alternate !== null && t.alternate.child === t.child,
      n = 0,
      l = 0;
    if (e)
      for (var a = t.child; a !== null; )
        ((n |= a.lanes | a.childLanes),
          (l |= a.subtreeFlags & 65011712),
          (l |= a.flags & 65011712),
          (a.return = t),
          (a = a.sibling));
    else
      for (a = t.child; a !== null; )
        ((n |= a.lanes | a.childLanes),
          (l |= a.subtreeFlags),
          (l |= a.flags),
          (a.return = t),
          (a = a.sibling));
    return ((t.subtreeFlags |= l), (t.childLanes = n), e);
  }
  function Fg(t, e, n) {
    var l = e.pendingProps;
    switch ((kr(e), e.tag)) {
      case 16:
      case 15:
      case 0:
      case 11:
      case 7:
      case 8:
      case 12:
      case 9:
      case 14:
        return (Kt(e), null);
      case 1:
        return (Kt(e), null);
      case 3:
        return (
          (n = e.stateNode),
          (l = null),
          t !== null && (l = t.memoizedState.cache),
          e.memoizedState.cache !== l && (e.flags |= 2048),
          yn(Pt),
          ut(),
          n.pendingContext &&
            ((n.context = n.pendingContext), (n.pendingContext = null)),
          (t === null || t.child === null) &&
            (Yl(e)
              ? xn(e)
              : t === null ||
                (t.memoizedState.isDehydrated && (e.flags & 256) === 0) ||
                ((e.flags |= 1024), Nr())),
          Kt(e),
          null
        );
      case 26:
        var a = e.type,
          o = e.memoizedState;
        return (
          t === null
            ? (xn(e),
              o !== null ? (Kt(e), Th(e, o)) : (Kt(e), zc(e, a, null, l, n)))
            : o
              ? o !== t.memoizedState
                ? (xn(e), Kt(e), Th(e, o))
                : (Kt(e), (e.flags &= -16777217))
              : ((t = t.memoizedProps),
                t !== l && xn(e),
                Kt(e),
                zc(e, a, t, l, n)),
          null
        );
      case 27:
        if (
          (me(e),
          (n = at.current),
          (a = e.type),
          t !== null && e.stateNode != null)
        )
          t.memoizedProps !== l && xn(e);
        else {
          if (!l) {
            if (e.stateNode === null) throw Error(c(166));
            return (Kt(e), null);
          }
          ((t = I.current),
            Yl(e) ? ls(e) : ((t = kd(a, l, n)), (e.stateNode = t), xn(e)));
        }
        return (Kt(e), null);
      case 5:
        if ((me(e), (a = e.type), t !== null && e.stateNode != null))
          t.memoizedProps !== l && xn(e);
        else {
          if (!l) {
            if (e.stateNode === null) throw Error(c(166));
            return (Kt(e), null);
          }
          if (((o = I.current), Yl(e))) ls(e);
          else {
            var h = Au(at.current);
            switch (o) {
              case 1:
                o = h.createElementNS("http://www.w3.org/2000/svg", a);
                break;
              case 2:
                o = h.createElementNS("http://www.w3.org/1998/Math/MathML", a);
                break;
              default:
                switch (a) {
                  case "svg":
                    o = h.createElementNS("http://www.w3.org/2000/svg", a);
                    break;
                  case "math":
                    o = h.createElementNS(
                      "http://www.w3.org/1998/Math/MathML",
                      a,
                    );
                    break;
                  case "script":
                    ((o = h.createElement("div")),
                      (o.innerHTML = "<script><\/script>"),
                      (o = o.removeChild(o.firstChild)));
                    break;
                  case "select":
                    ((o =
                      typeof l.is == "string"
                        ? h.createElement("select", { is: l.is })
                        : h.createElement("select")),
                      l.multiple
                        ? (o.multiple = !0)
                        : l.size && (o.size = l.size));
                    break;
                  default:
                    o =
                      typeof l.is == "string"
                        ? h.createElement(a, { is: l.is })
                        : h.createElement(a);
                }
            }
            ((o[ce] = e), (o[Se] = l));
            t: for (h = e.child; h !== null; ) {
              if (h.tag === 5 || h.tag === 6) o.appendChild(h.stateNode);
              else if (h.tag !== 4 && h.tag !== 27 && h.child !== null) {
                ((h.child.return = h), (h = h.child));
                continue;
              }
              if (h === e) break t;
              for (; h.sibling === null; ) {
                if (h.return === null || h.return === e) break t;
                h = h.return;
              }
              ((h.sibling.return = h.return), (h = h.sibling));
            }
            e.stateNode = o;
            t: switch ((he(o, a, l), a)) {
              case "button":
              case "input":
              case "select":
              case "textarea":
                l = !!l.autoFocus;
                break t;
              case "img":
                l = !0;
                break t;
              default:
                l = !1;
            }
            l && xn(e);
          }
        }
        return (
          Kt(e),
          zc(e, e.type, t === null ? null : t.memoizedProps, e.pendingProps, n),
          null
        );
      case 6:
        if (t && e.stateNode != null) t.memoizedProps !== l && xn(e);
        else {
          if (typeof l != "string" && e.stateNode === null) throw Error(c(166));
          if (((t = at.current), Yl(e))) {
            if (
              ((t = e.stateNode),
              (n = e.memoizedProps),
              (l = null),
              (a = oe),
              a !== null)
            )
              switch (a.tag) {
                case 27:
                case 5:
                  l = a.memoizedProps;
              }
            ((t[ce] = e),
              (t = !!(
                t.nodeValue === n ||
                (l !== null && l.suppressHydrationWarning === !0) ||
                Sd(t.nodeValue, n)
              )),
              t || Rn(e, !0));
          } else
            ((t = Au(t).createTextNode(l)), (t[ce] = e), (e.stateNode = t));
        }
        return (Kt(e), null);
      case 31:
        if (((n = e.memoizedState), t === null || t.memoizedState !== null)) {
          if (((l = Yl(e)), n !== null)) {
            if (t === null) {
              if (!l) throw Error(c(318));
              if (
                ((t = e.memoizedState),
                (t = t !== null ? t.dehydrated : null),
                !t)
              )
                throw Error(c(557));
              t[ce] = e;
            } else
              (ol(),
                (e.flags & 128) === 0 && (e.memoizedState = null),
                (e.flags |= 4));
            (Kt(e), (t = !1));
          } else
            ((n = Nr()),
              t !== null &&
                t.memoizedState !== null &&
                (t.memoizedState.hydrationErrors = n),
              (t = !0));
          if (!t) return e.flags & 256 ? (Re(e), e) : (Re(e), null);
          if ((e.flags & 128) !== 0) throw Error(c(558));
        }
        return (Kt(e), null);
      case 13:
        if (
          ((l = e.memoizedState),
          t === null ||
            (t.memoizedState !== null && t.memoizedState.dehydrated !== null))
        ) {
          if (((a = Yl(e)), l !== null && l.dehydrated !== null)) {
            if (t === null) {
              if (!a) throw Error(c(318));
              if (
                ((a = e.memoizedState),
                (a = a !== null ? a.dehydrated : null),
                !a)
              )
                throw Error(c(317));
              a[ce] = e;
            } else
              (ol(),
                (e.flags & 128) === 0 && (e.memoizedState = null),
                (e.flags |= 4));
            (Kt(e), (a = !1));
          } else
            ((a = Nr()),
              t !== null &&
                t.memoizedState !== null &&
                (t.memoizedState.hydrationErrors = a),
              (a = !0));
          if (!a) return e.flags & 256 ? (Re(e), e) : (Re(e), null);
        }
        return (
          Re(e),
          (e.flags & 128) !== 0
            ? ((e.lanes = n), e)
            : ((n = l !== null),
              (t = t !== null && t.memoizedState !== null),
              n &&
                ((l = e.child),
                (a = null),
                l.alternate !== null &&
                  l.alternate.memoizedState !== null &&
                  l.alternate.memoizedState.cachePool !== null &&
                  (a = l.alternate.memoizedState.cachePool.pool),
                (o = null),
                l.memoizedState !== null &&
                  l.memoizedState.cachePool !== null &&
                  (o = l.memoizedState.cachePool.pool),
                o !== a && (l.flags |= 2048)),
              n !== t && n && (e.child.flags |= 8192),
              fu(e, e.updateQueue),
              Kt(e),
              null)
        );
      case 4:
        return (ut(), t === null && Vc(e.stateNode.containerInfo), Kt(e), null);
      case 10:
        return (yn(e.type), Kt(e), null);
      case 19:
        if ((U(Wt), (l = e.memoizedState), l === null)) return (Kt(e), null);
        if (((a = (e.flags & 128) !== 0), (o = l.rendering), o === null))
          if (a) Qi(l, !1);
          else {
            if (It !== 0 || (t !== null && (t.flags & 128) !== 0))
              for (t = e.child; t !== null; ) {
                if (((o = Wa(t)), o !== null)) {
                  for (
                    e.flags |= 128,
                      Qi(l, !1),
                      t = o.updateQueue,
                      e.updateQueue = t,
                      fu(e, t),
                      e.subtreeFlags = 0,
                      t = n,
                      n = e.child;
                    n !== null;
                  )
                    ($f(n, t), (n = n.sibling));
                  return (
                    S(Wt, (Wt.current & 1) | 2),
                    Mt && mn(e, l.treeForkCount),
                    e.child
                  );
                }
                t = t.sibling;
              }
            l.tail !== null &&
              ge() > mu &&
              ((e.flags |= 128), (a = !0), Qi(l, !1), (e.lanes = 4194304));
          }
        else {
          if (!a)
            if (((t = Wa(o)), t !== null)) {
              if (
                ((e.flags |= 128),
                (a = !0),
                (t = t.updateQueue),
                (e.updateQueue = t),
                fu(e, t),
                Qi(l, !0),
                l.tail === null &&
                  l.tailMode === "hidden" &&
                  !o.alternate &&
                  !Mt)
              )
                return (Kt(e), null);
            } else
              2 * ge() - l.renderingStartTime > mu &&
                n !== 536870912 &&
                ((e.flags |= 128), (a = !0), Qi(l, !1), (e.lanes = 4194304));
          l.isBackwards
            ? ((o.sibling = e.child), (e.child = o))
            : ((t = l.last),
              t !== null ? (t.sibling = o) : (e.child = o),
              (l.last = o));
        }
        return l.tail !== null
          ? ((t = l.tail),
            (l.rendering = t),
            (l.tail = t.sibling),
            (l.renderingStartTime = ge()),
            (t.sibling = null),
            (n = Wt.current),
            S(Wt, a ? (n & 1) | 2 : n & 1),
            Mt && mn(e, l.treeForkCount),
            t)
          : (Kt(e), null);
      case 22:
      case 23:
        return (
          Re(e),
          Zr(),
          (l = e.memoizedState !== null),
          t !== null
            ? (t.memoizedState !== null) !== l && (e.flags |= 8192)
            : l && (e.flags |= 8192),
          l
            ? (n & 536870912) !== 0 &&
              (e.flags & 128) === 0 &&
              (Kt(e), e.subtreeFlags & 6 && (e.flags |= 8192))
            : Kt(e),
          (n = e.updateQueue),
          n !== null && fu(e, n.retryQueue),
          (n = null),
          t !== null &&
            t.memoizedState !== null &&
            t.memoizedState.cachePool !== null &&
            (n = t.memoizedState.cachePool.pool),
          (l = null),
          e.memoizedState !== null &&
            e.memoizedState.cachePool !== null &&
            (l = e.memoizedState.cachePool.pool),
          l !== n && (e.flags |= 2048),
          t !== null && U(hl),
          null
        );
      case 24:
        return (
          (n = null),
          t !== null && (n = t.memoizedState.cache),
          e.memoizedState.cache !== n && (e.flags |= 2048),
          yn(Pt),
          Kt(e),
          null
        );
      case 25:
        return null;
      case 30:
        return null;
    }
    throw Error(c(156, e.tag));
  }
  function Ig(t, e) {
    switch ((kr(e), e.tag)) {
      case 1:
        return (
          (t = e.flags),
          t & 65536 ? ((e.flags = (t & -65537) | 128), e) : null
        );
      case 3:
        return (
          yn(Pt),
          ut(),
          (t = e.flags),
          (t & 65536) !== 0 && (t & 128) === 0
            ? ((e.flags = (t & -65537) | 128), e)
            : null
        );
      case 26:
      case 27:
      case 5:
        return (me(e), null);
      case 31:
        if (e.memoizedState !== null) {
          if ((Re(e), e.alternate === null)) throw Error(c(340));
          ol();
        }
        return (
          (t = e.flags),
          t & 65536 ? ((e.flags = (t & -65537) | 128), e) : null
        );
      case 13:
        if (
          (Re(e), (t = e.memoizedState), t !== null && t.dehydrated !== null)
        ) {
          if (e.alternate === null) throw Error(c(340));
          ol();
        }
        return (
          (t = e.flags),
          t & 65536 ? ((e.flags = (t & -65537) | 128), e) : null
        );
      case 19:
        return (U(Wt), null);
      case 4:
        return (ut(), null);
      case 10:
        return (yn(e.type), null);
      case 22:
      case 23:
        return (
          Re(e),
          Zr(),
          t !== null && U(hl),
          (t = e.flags),
          t & 65536 ? ((e.flags = (t & -65537) | 128), e) : null
        );
      case 24:
        return (yn(Pt), null);
      case 25:
        return null;
      default:
        return null;
    }
  }
  function Ah(t, e) {
    switch ((kr(e), e.tag)) {
      case 3:
        (yn(Pt), ut());
        break;
      case 26:
      case 27:
      case 5:
        me(e);
        break;
      case 4:
        ut();
        break;
      case 31:
        e.memoizedState !== null && Re(e);
        break;
      case 13:
        Re(e);
        break;
      case 19:
        U(Wt);
        break;
      case 10:
        yn(e.type);
        break;
      case 22:
      case 23:
        (Re(e), Zr(), t !== null && U(hl));
        break;
      case 24:
        yn(Pt);
    }
  }
  function Vi(t, e) {
    try {
      var n = e.updateQueue,
        l = n !== null ? n.lastEffect : null;
      if (l !== null) {
        var a = l.next;
        n = a;
        do {
          if ((n.tag & t) === t) {
            l = void 0;
            var o = n.create,
              h = n.inst;
            ((l = o()), (h.destroy = l));
          }
          n = n.next;
        } while (n !== a);
      }
    } catch (g) {
      Ht(e, e.return, g);
    }
  }
  function Yn(t, e, n) {
    try {
      var l = e.updateQueue,
        a = l !== null ? l.lastEffect : null;
      if (a !== null) {
        var o = a.next;
        l = o;
        do {
          if ((l.tag & t) === t) {
            var h = l.inst,
              g = h.destroy;
            if (g !== void 0) {
              ((h.destroy = void 0), (a = e));
              var z = n,
                D = g;
              try {
                D();
              } catch (N) {
                Ht(a, z, N);
              }
            }
          }
          l = l.next;
        } while (l !== o);
      }
    } catch (N) {
      Ht(e, e.return, N);
    }
  }
  function Ch(t) {
    var e = t.updateQueue;
    if (e !== null) {
      var n = t.stateNode;
      try {
        gs(e, n);
      } catch (l) {
        Ht(t, t.return, l);
      }
    }
  }
  function _h(t, e, n) {
    ((n.props = yl(t.type, t.memoizedProps)), (n.state = t.memoizedState));
    try {
      n.componentWillUnmount();
    } catch (l) {
      Ht(t, e, l);
    }
  }
  function Zi(t, e) {
    try {
      var n = t.ref;
      if (n !== null) {
        switch (t.tag) {
          case 26:
          case 27:
          case 5:
            var l = t.stateNode;
            break;
          case 30:
            l = t.stateNode;
            break;
          default:
            l = t.stateNode;
        }
        typeof n == "function" ? (t.refCleanup = n(l)) : (n.current = l);
      }
    } catch (a) {
      Ht(t, e, a);
    }
  }
  function ln(t, e) {
    var n = t.ref,
      l = t.refCleanup;
    if (n !== null)
      if (typeof l == "function")
        try {
          l();
        } catch (a) {
          Ht(t, e, a);
        } finally {
          ((t.refCleanup = null),
            (t = t.alternate),
            t != null && (t.refCleanup = null));
        }
      else if (typeof n == "function")
        try {
          n(null);
        } catch (a) {
          Ht(t, e, a);
        }
      else n.current = null;
  }
  function Oh(t) {
    var e = t.type,
      n = t.memoizedProps,
      l = t.stateNode;
    try {
      t: switch (e) {
        case "button":
        case "input":
        case "select":
        case "textarea":
          n.autoFocus && l.focus();
          break t;
        case "img":
          n.src ? (l.src = n.src) : n.srcSet && (l.srcset = n.srcSet);
      }
    } catch (a) {
      Ht(t, t.return, a);
    }
  }
  function Tc(t, e, n) {
    try {
      var l = t.stateNode;
      (by(l, t.type, n, e), (l[Se] = e));
    } catch (a) {
      Ht(t, t.return, a);
    }
  }
  function Dh(t) {
    return (
      t.tag === 5 ||
      t.tag === 3 ||
      t.tag === 26 ||
      (t.tag === 27 && Jn(t.type)) ||
      t.tag === 4
    );
  }
  function Ac(t) {
    t: for (;;) {
      for (; t.sibling === null; ) {
        if (t.return === null || Dh(t.return)) return null;
        t = t.return;
      }
      for (
        t.sibling.return = t.return, t = t.sibling;
        t.tag !== 5 && t.tag !== 6 && t.tag !== 18;
      ) {
        if (
          (t.tag === 27 && Jn(t.type)) ||
          t.flags & 2 ||
          t.child === null ||
          t.tag === 4
        )
          continue t;
        ((t.child.return = t), (t = t.child));
      }
      if (!(t.flags & 2)) return t.stateNode;
    }
  }
  function Cc(t, e, n) {
    var l = t.tag;
    if (l === 5 || l === 6)
      ((t = t.stateNode),
        e
          ? (n.nodeType === 9
              ? n.body
              : n.nodeName === "HTML"
                ? n.ownerDocument.body
                : n
            ).insertBefore(t, e)
          : ((e =
              n.nodeType === 9
                ? n.body
                : n.nodeName === "HTML"
                  ? n.ownerDocument.body
                  : n),
            e.appendChild(t),
            (n = n._reactRootContainer),
            n != null || e.onclick !== null || (e.onclick = hn)));
    else if (
      l !== 4 &&
      (l === 27 && Jn(t.type) && ((n = t.stateNode), (e = null)),
      (t = t.child),
      t !== null)
    )
      for (Cc(t, e, n), t = t.sibling; t !== null; )
        (Cc(t, e, n), (t = t.sibling));
  }
  function su(t, e, n) {
    var l = t.tag;
    if (l === 5 || l === 6)
      ((t = t.stateNode), e ? n.insertBefore(t, e) : n.appendChild(t));
    else if (
      l !== 4 &&
      (l === 27 && Jn(t.type) && (n = t.stateNode), (t = t.child), t !== null)
    )
      for (su(t, e, n), t = t.sibling; t !== null; )
        (su(t, e, n), (t = t.sibling));
  }
  function Mh(t) {
    var e = t.stateNode,
      n = t.memoizedProps;
    try {
      for (var l = t.type, a = e.attributes; a.length; )
        e.removeAttributeNode(a[0]);
      (he(e, l, n), (e[ce] = t), (e[Se] = n));
    } catch (o) {
      Ht(t, t.return, o);
    }
  }
  var En = !1,
    ne = !1,
    _c = !1,
    kh = typeof WeakSet == "function" ? WeakSet : Set,
    re = null;
  function Wg(t, e) {
    if (((t = t.containerInfo), (Jc = wu), (t = Xf(t)), Sr(t))) {
      if ("selectionStart" in t)
        var n = { start: t.selectionStart, end: t.selectionEnd };
      else
        t: {
          n = ((n = t.ownerDocument) && n.defaultView) || window;
          var l = n.getSelection && n.getSelection();
          if (l && l.rangeCount !== 0) {
            n = l.anchorNode;
            var a = l.anchorOffset,
              o = l.focusNode;
            l = l.focusOffset;
            try {
              (n.nodeType, o.nodeType);
            } catch {
              n = null;
              break t;
            }
            var h = 0,
              g = -1,
              z = -1,
              D = 0,
              N = 0,
              q = t,
              k = null;
            e: for (;;) {
              for (
                var w;
                q !== n || (a !== 0 && q.nodeType !== 3) || (g = h + a),
                  q !== o || (l !== 0 && q.nodeType !== 3) || (z = h + l),
                  q.nodeType === 3 && (h += q.nodeValue.length),
                  (w = q.firstChild) !== null;
              )
                ((k = q), (q = w));
              for (;;) {
                if (q === t) break e;
                if (
                  (k === n && ++D === a && (g = h),
                  k === o && ++N === l && (z = h),
                  (w = q.nextSibling) !== null)
                )
                  break;
                ((q = k), (k = q.parentNode));
              }
              q = w;
            }
            n = g === -1 || z === -1 ? null : { start: g, end: z };
          } else n = null;
        }
      n = n || { start: 0, end: 0 };
    } else n = null;
    for (
      Fc = { focusedElem: t, selectionRange: n }, wu = !1, re = e;
      re !== null;
    )
      if (
        ((e = re), (t = e.child), (e.subtreeFlags & 1028) !== 0 && t !== null)
      )
        ((t.return = e), (re = t));
      else
        for (; re !== null; ) {
          switch (((e = re), (o = e.alternate), (t = e.flags), e.tag)) {
            case 0:
              if (
                (t & 4) !== 0 &&
                ((t = e.updateQueue),
                (t = t !== null ? t.events : null),
                t !== null)
              )
                for (n = 0; n < t.length; n++)
                  ((a = t[n]), (a.ref.impl = a.nextImpl));
              break;
            case 11:
            case 15:
              break;
            case 1:
              if ((t & 1024) !== 0 && o !== null) {
                ((t = void 0),
                  (n = e),
                  (a = o.memoizedProps),
                  (o = o.memoizedState),
                  (l = n.stateNode));
                try {
                  var et = yl(n.type, a);
                  ((t = l.getSnapshotBeforeUpdate(et, o)),
                    (l.__reactInternalSnapshotBeforeUpdate = t));
                } catch (ot) {
                  Ht(n, n.return, ot);
                }
              }
              break;
            case 3:
              if ((t & 1024) !== 0) {
                if (
                  ((t = e.stateNode.containerInfo), (n = t.nodeType), n === 9)
                )
                  $c(t);
                else if (n === 1)
                  switch (t.nodeName) {
                    case "HEAD":
                    case "HTML":
                    case "BODY":
                      $c(t);
                      break;
                    default:
                      t.textContent = "";
                  }
              }
              break;
            case 5:
            case 26:
            case 27:
            case 6:
            case 4:
            case 17:
              break;
            default:
              if ((t & 1024) !== 0) throw Error(c(163));
          }
          if (((t = e.sibling), t !== null)) {
            ((t.return = e.return), (re = t));
            break;
          }
          re = e.return;
        }
  }
  function wh(t, e, n) {
    var l = n.flags;
    switch (n.tag) {
      case 0:
      case 11:
      case 15:
        (Tn(t, n), l & 4 && Vi(5, n));
        break;
      case 1:
        if ((Tn(t, n), l & 4))
          if (((t = n.stateNode), e === null))
            try {
              t.componentDidMount();
            } catch (h) {
              Ht(n, n.return, h);
            }
          else {
            var a = yl(n.type, e.memoizedProps);
            e = e.memoizedState;
            try {
              t.componentDidUpdate(a, e, t.__reactInternalSnapshotBeforeUpdate);
            } catch (h) {
              Ht(n, n.return, h);
            }
          }
        (l & 64 && Ch(n), l & 512 && Zi(n, n.return));
        break;
      case 3:
        if ((Tn(t, n), l & 64 && ((t = n.updateQueue), t !== null))) {
          if (((e = null), n.child !== null))
            switch (n.child.tag) {
              case 27:
              case 5:
                e = n.child.stateNode;
                break;
              case 1:
                e = n.child.stateNode;
            }
          try {
            gs(t, e);
          } catch (h) {
            Ht(n, n.return, h);
          }
        }
        break;
      case 27:
        e === null && l & 4 && Mh(n);
      case 26:
      case 5:
        (Tn(t, n), e === null && l & 4 && Oh(n), l & 512 && Zi(n, n.return));
        break;
      case 12:
        Tn(t, n);
        break;
      case 31:
        (Tn(t, n), l & 4 && Uh(t, n));
        break;
      case 13:
        (Tn(t, n),
          l & 4 && Bh(t, n),
          l & 64 &&
            ((t = n.memoizedState),
            t !== null &&
              ((t = t.dehydrated),
              t !== null && ((n = uy.bind(null, n)), Cy(t, n)))));
        break;
      case 22:
        if (((l = n.memoizedState !== null || En), !l)) {
          ((e = (e !== null && e.memoizedState !== null) || ne), (a = En));
          var o = ne;
          ((En = l),
            (ne = e) && !o ? An(t, n, (n.subtreeFlags & 8772) !== 0) : Tn(t, n),
            (En = a),
            (ne = o));
        }
        break;
      case 30:
        break;
      default:
        Tn(t, n);
    }
  }
  function Nh(t) {
    var e = t.alternate;
    (e !== null && ((t.alternate = null), Nh(e)),
      (t.child = null),
      (t.deletions = null),
      (t.sibling = null),
      t.tag === 5 && ((e = t.stateNode), e !== null && lr(e)),
      (t.stateNode = null),
      (t.return = null),
      (t.dependencies = null),
      (t.memoizedProps = null),
      (t.memoizedState = null),
      (t.pendingProps = null),
      (t.stateNode = null),
      (t.updateQueue = null));
  }
  var Jt = null,
    Ee = !1;
  function zn(t, e, n) {
    for (n = n.child; n !== null; ) (Rh(t, e, n), (n = n.sibling));
  }
  function Rh(t, e, n) {
    if (ie && typeof ie.onCommitFiberUnmount == "function")
      try {
        ie.onCommitFiberUnmount(ye, n);
      } catch {}
    switch (n.tag) {
      case 26:
        (ne || ln(n, e),
          zn(t, e, n),
          n.memoizedState
            ? n.memoizedState.count--
            : n.stateNode && ((n = n.stateNode), n.parentNode.removeChild(n)));
        break;
      case 27:
        ne || ln(n, e);
        var l = Jt,
          a = Ee;
        (Jn(n.type) && ((Jt = n.stateNode), (Ee = !1)),
          zn(t, e, n),
          ea(n.stateNode),
          (Jt = l),
          (Ee = a));
        break;
      case 5:
        ne || ln(n, e);
      case 6:
        if (
          ((l = Jt),
          (a = Ee),
          (Jt = null),
          zn(t, e, n),
          (Jt = l),
          (Ee = a),
          Jt !== null)
        )
          if (Ee)
            try {
              (Jt.nodeType === 9
                ? Jt.body
                : Jt.nodeName === "HTML"
                  ? Jt.ownerDocument.body
                  : Jt
              ).removeChild(n.stateNode);
            } catch (o) {
              Ht(n, e, o);
            }
          else
            try {
              Jt.removeChild(n.stateNode);
            } catch (o) {
              Ht(n, e, o);
            }
        break;
      case 18:
        Jt !== null &&
          (Ee
            ? ((t = Jt),
              Cd(
                t.nodeType === 9
                  ? t.body
                  : t.nodeName === "HTML"
                    ? t.ownerDocument.body
                    : t,
                n.stateNode,
              ),
              ci(t))
            : Cd(Jt, n.stateNode));
        break;
      case 4:
        ((l = Jt),
          (a = Ee),
          (Jt = n.stateNode.containerInfo),
          (Ee = !0),
          zn(t, e, n),
          (Jt = l),
          (Ee = a));
        break;
      case 0:
      case 11:
      case 14:
      case 15:
        (Yn(2, n, e), ne || Yn(4, n, e), zn(t, e, n));
        break;
      case 1:
        (ne ||
          (ln(n, e),
          (l = n.stateNode),
          typeof l.componentWillUnmount == "function" && _h(n, e, l)),
          zn(t, e, n));
        break;
      case 21:
        zn(t, e, n);
        break;
      case 22:
        ((ne = (l = ne) || n.memoizedState !== null), zn(t, e, n), (ne = l));
        break;
      default:
        zn(t, e, n);
    }
  }
  function Uh(t, e) {
    if (
      e.memoizedState === null &&
      ((t = e.alternate), t !== null && ((t = t.memoizedState), t !== null))
    ) {
      t = t.dehydrated;
      try {
        ci(t);
      } catch (n) {
        Ht(e, e.return, n);
      }
    }
  }
  function Bh(t, e) {
    if (
      e.memoizedState === null &&
      ((t = e.alternate),
      t !== null &&
        ((t = t.memoizedState), t !== null && ((t = t.dehydrated), t !== null)))
    )
      try {
        ci(t);
      } catch (n) {
        Ht(e, e.return, n);
      }
  }
  function $g(t) {
    switch (t.tag) {
      case 31:
      case 13:
      case 19:
        var e = t.stateNode;
        return (e === null && (e = t.stateNode = new kh()), e);
      case 22:
        return (
          (t = t.stateNode),
          (e = t._retryCache),
          e === null && (e = t._retryCache = new kh()),
          e
        );
      default:
        throw Error(c(435, t.tag));
    }
  }
  function hu(t, e) {
    var n = $g(t);
    e.forEach(function (l) {
      if (!n.has(l)) {
        n.add(l);
        var a = ry.bind(null, t, l);
        l.then(a, a);
      }
    });
  }
  function ze(t, e) {
    var n = e.deletions;
    if (n !== null)
      for (var l = 0; l < n.length; l++) {
        var a = n[l],
          o = t,
          h = e,
          g = h;
        t: for (; g !== null; ) {
          switch (g.tag) {
            case 27:
              if (Jn(g.type)) {
                ((Jt = g.stateNode), (Ee = !1));
                break t;
              }
              break;
            case 5:
              ((Jt = g.stateNode), (Ee = !1));
              break t;
            case 3:
            case 4:
              ((Jt = g.stateNode.containerInfo), (Ee = !0));
              break t;
          }
          g = g.return;
        }
        if (Jt === null) throw Error(c(160));
        (Rh(o, h, a),
          (Jt = null),
          (Ee = !1),
          (o = a.alternate),
          o !== null && (o.return = null),
          (a.return = null));
      }
    if (e.subtreeFlags & 13886)
      for (e = e.child; e !== null; ) (jh(e, t), (e = e.sibling));
  }
  var Pe = null;
  function jh(t, e) {
    var n = t.alternate,
      l = t.flags;
    switch (t.tag) {
      case 0:
      case 11:
      case 14:
      case 15:
        (ze(e, t),
          Te(t),
          l & 4 && (Yn(3, t, t.return), Vi(3, t), Yn(5, t, t.return)));
        break;
      case 1:
        (ze(e, t),
          Te(t),
          l & 512 && (ne || n === null || ln(n, n.return)),
          l & 64 &&
            En &&
            ((t = t.updateQueue),
            t !== null &&
              ((l = t.callbacks),
              l !== null &&
                ((n = t.shared.hiddenCallbacks),
                (t.shared.hiddenCallbacks = n === null ? l : n.concat(l))))));
        break;
      case 26:
        var a = Pe;
        if (
          (ze(e, t),
          Te(t),
          l & 512 && (ne || n === null || ln(n, n.return)),
          l & 4)
        ) {
          var o = n !== null ? n.memoizedState : null;
          if (((l = t.memoizedState), n === null))
            if (l === null)
              if (t.stateNode === null) {
                t: {
                  ((l = t.type),
                    (n = t.memoizedProps),
                    (a = a.ownerDocument || a));
                  e: switch (l) {
                    case "title":
                      ((o = a.getElementsByTagName("title")[0]),
                        (!o ||
                          o[vi] ||
                          o[ce] ||
                          o.namespaceURI === "http://www.w3.org/2000/svg" ||
                          o.hasAttribute("itemprop")) &&
                          ((o = a.createElement(l)),
                          a.head.insertBefore(
                            o,
                            a.querySelector("head > title"),
                          )),
                        he(o, l, n),
                        (o[ce] = t),
                        ue(o),
                        (l = o));
                      break t;
                    case "link":
                      var h = jd("link", "href", a).get(l + (n.href || ""));
                      if (h) {
                        for (var g = 0; g < h.length; g++)
                          if (
                            ((o = h[g]),
                            o.getAttribute("href") ===
                              (n.href == null || n.href === ""
                                ? null
                                : n.href) &&
                              o.getAttribute("rel") ===
                                (n.rel == null ? null : n.rel) &&
                              o.getAttribute("title") ===
                                (n.title == null ? null : n.title) &&
                              o.getAttribute("crossorigin") ===
                                (n.crossOrigin == null ? null : n.crossOrigin))
                          ) {
                            h.splice(g, 1);
                            break e;
                          }
                      }
                      ((o = a.createElement(l)),
                        he(o, l, n),
                        a.head.appendChild(o));
                      break;
                    case "meta":
                      if (
                        (h = jd("meta", "content", a).get(
                          l + (n.content || ""),
                        ))
                      ) {
                        for (g = 0; g < h.length; g++)
                          if (
                            ((o = h[g]),
                            o.getAttribute("content") ===
                              (n.content == null ? null : "" + n.content) &&
                              o.getAttribute("name") ===
                                (n.name == null ? null : n.name) &&
                              o.getAttribute("property") ===
                                (n.property == null ? null : n.property) &&
                              o.getAttribute("http-equiv") ===
                                (n.httpEquiv == null ? null : n.httpEquiv) &&
                              o.getAttribute("charset") ===
                                (n.charSet == null ? null : n.charSet))
                          ) {
                            h.splice(g, 1);
                            break e;
                          }
                      }
                      ((o = a.createElement(l)),
                        he(o, l, n),
                        a.head.appendChild(o));
                      break;
                    default:
                      throw Error(c(468, l));
                  }
                  ((o[ce] = t), ue(o), (l = o));
                }
                t.stateNode = l;
              } else Hd(a, t.type, t.stateNode);
            else t.stateNode = Bd(a, l, t.memoizedProps);
          else
            o !== l
              ? (o === null
                  ? n.stateNode !== null &&
                    ((n = n.stateNode), n.parentNode.removeChild(n))
                  : o.count--,
                l === null
                  ? Hd(a, t.type, t.stateNode)
                  : Bd(a, l, t.memoizedProps))
              : l === null &&
                t.stateNode !== null &&
                Tc(t, t.memoizedProps, n.memoizedProps);
        }
        break;
      case 27:
        (ze(e, t),
          Te(t),
          l & 512 && (ne || n === null || ln(n, n.return)),
          n !== null && l & 4 && Tc(t, t.memoizedProps, n.memoizedProps));
        break;
      case 5:
        if (
          (ze(e, t),
          Te(t),
          l & 512 && (ne || n === null || ln(n, n.return)),
          t.flags & 32)
        ) {
          a = t.stateNode;
          try {
            kl(a, "");
          } catch (et) {
            Ht(t, t.return, et);
          }
        }
        (l & 4 &&
          t.stateNode != null &&
          ((a = t.memoizedProps), Tc(t, a, n !== null ? n.memoizedProps : a)),
          l & 1024 && (_c = !0));
        break;
      case 6:
        if ((ze(e, t), Te(t), l & 4)) {
          if (t.stateNode === null) throw Error(c(162));
          ((l = t.memoizedProps), (n = t.stateNode));
          try {
            n.nodeValue = l;
          } catch (et) {
            Ht(t, t.return, et);
          }
        }
        break;
      case 3:
        if (
          ((Ou = null),
          (a = Pe),
          (Pe = Cu(e.containerInfo)),
          ze(e, t),
          (Pe = a),
          Te(t),
          l & 4 && n !== null && n.memoizedState.isDehydrated)
        )
          try {
            ci(e.containerInfo);
          } catch (et) {
            Ht(t, t.return, et);
          }
        _c && ((_c = !1), Hh(t));
        break;
      case 4:
        ((l = Pe),
          (Pe = Cu(t.stateNode.containerInfo)),
          ze(e, t),
          Te(t),
          (Pe = l));
        break;
      case 12:
        (ze(e, t), Te(t));
        break;
      case 31:
        (ze(e, t),
          Te(t),
          l & 4 &&
            ((l = t.updateQueue),
            l !== null && ((t.updateQueue = null), hu(t, l))));
        break;
      case 13:
        (ze(e, t),
          Te(t),
          t.child.flags & 8192 &&
            (t.memoizedState !== null) !=
              (n !== null && n.memoizedState !== null) &&
            (pu = ge()),
          l & 4 &&
            ((l = t.updateQueue),
            l !== null && ((t.updateQueue = null), hu(t, l))));
        break;
      case 22:
        a = t.memoizedState !== null;
        var z = n !== null && n.memoizedState !== null,
          D = En,
          N = ne;
        if (
          ((En = D || a),
          (ne = N || z),
          ze(e, t),
          (ne = N),
          (En = D),
          Te(t),
          l & 8192)
        )
          t: for (
            e = t.stateNode,
              e._visibility = a ? e._visibility & -2 : e._visibility | 1,
              a && (n === null || z || En || ne || bl(t)),
              n = null,
              e = t;
            ;
          ) {
            if (e.tag === 5 || e.tag === 26) {
              if (n === null) {
                z = n = e;
                try {
                  if (((o = z.stateNode), a))
                    ((h = o.style),
                      typeof h.setProperty == "function"
                        ? h.setProperty("display", "none", "important")
                        : (h.display = "none"));
                  else {
                    g = z.stateNode;
                    var q = z.memoizedProps.style,
                      k =
                        q != null && q.hasOwnProperty("display")
                          ? q.display
                          : null;
                    g.style.display =
                      k == null || typeof k == "boolean" ? "" : ("" + k).trim();
                  }
                } catch (et) {
                  Ht(z, z.return, et);
                }
              }
            } else if (e.tag === 6) {
              if (n === null) {
                z = e;
                try {
                  z.stateNode.nodeValue = a ? "" : z.memoizedProps;
                } catch (et) {
                  Ht(z, z.return, et);
                }
              }
            } else if (e.tag === 18) {
              if (n === null) {
                z = e;
                try {
                  var w = z.stateNode;
                  a ? _d(w, !0) : _d(z.stateNode, !1);
                } catch (et) {
                  Ht(z, z.return, et);
                }
              }
            } else if (
              ((e.tag !== 22 && e.tag !== 23) ||
                e.memoizedState === null ||
                e === t) &&
              e.child !== null
            ) {
              ((e.child.return = e), (e = e.child));
              continue;
            }
            if (e === t) break t;
            for (; e.sibling === null; ) {
              if (e.return === null || e.return === t) break t;
              (n === e && (n = null), (e = e.return));
            }
            (n === e && (n = null),
              (e.sibling.return = e.return),
              (e = e.sibling));
          }
        l & 4 &&
          ((l = t.updateQueue),
          l !== null &&
            ((n = l.retryQueue),
            n !== null && ((l.retryQueue = null), hu(t, n))));
        break;
      case 19:
        (ze(e, t),
          Te(t),
          l & 4 &&
            ((l = t.updateQueue),
            l !== null && ((t.updateQueue = null), hu(t, l))));
        break;
      case 30:
        break;
      case 21:
        break;
      default:
        (ze(e, t), Te(t));
    }
  }
  function Te(t) {
    var e = t.flags;
    if (e & 2) {
      try {
        for (var n, l = t.return; l !== null; ) {
          if (Dh(l)) {
            n = l;
            break;
          }
          l = l.return;
        }
        if (n == null) throw Error(c(160));
        switch (n.tag) {
          case 27:
            var a = n.stateNode,
              o = Ac(t);
            su(t, o, a);
            break;
          case 5:
            var h = n.stateNode;
            n.flags & 32 && (kl(h, ""), (n.flags &= -33));
            var g = Ac(t);
            su(t, g, h);
            break;
          case 3:
          case 4:
            var z = n.stateNode.containerInfo,
              D = Ac(t);
            Cc(t, D, z);
            break;
          default:
            throw Error(c(161));
        }
      } catch (N) {
        Ht(t, t.return, N);
      }
      t.flags &= -3;
    }
    e & 4096 && (t.flags &= -4097);
  }
  function Hh(t) {
    if (t.subtreeFlags & 1024)
      for (t = t.child; t !== null; ) {
        var e = t;
        (Hh(e),
          e.tag === 5 && e.flags & 1024 && e.stateNode.reset(),
          (t = t.sibling));
      }
  }
  function Tn(t, e) {
    if (e.subtreeFlags & 8772)
      for (e = e.child; e !== null; ) (wh(t, e.alternate, e), (e = e.sibling));
  }
  function bl(t) {
    for (t = t.child; t !== null; ) {
      var e = t;
      switch (e.tag) {
        case 0:
        case 11:
        case 14:
        case 15:
          (Yn(4, e, e.return), bl(e));
          break;
        case 1:
          ln(e, e.return);
          var n = e.stateNode;
          (typeof n.componentWillUnmount == "function" && _h(e, e.return, n),
            bl(e));
          break;
        case 27:
          ea(e.stateNode);
        case 26:
        case 5:
          (ln(e, e.return), bl(e));
          break;
        case 22:
          e.memoizedState === null && bl(e);
          break;
        case 30:
          bl(e);
          break;
        default:
          bl(e);
      }
      t = t.sibling;
    }
  }
  function An(t, e, n) {
    for (n = n && (e.subtreeFlags & 8772) !== 0, e = e.child; e !== null; ) {
      var l = e.alternate,
        a = t,
        o = e,
        h = o.flags;
      switch (o.tag) {
        case 0:
        case 11:
        case 15:
          (An(a, o, n), Vi(4, o));
          break;
        case 1:
          if (
            (An(a, o, n),
            (l = o),
            (a = l.stateNode),
            typeof a.componentDidMount == "function")
          )
            try {
              a.componentDidMount();
            } catch (D) {
              Ht(l, l.return, D);
            }
          if (((l = o), (a = l.updateQueue), a !== null)) {
            var g = l.stateNode;
            try {
              var z = a.shared.hiddenCallbacks;
              if (z !== null)
                for (a.shared.hiddenCallbacks = null, a = 0; a < z.length; a++)
                  ms(z[a], g);
            } catch (D) {
              Ht(l, l.return, D);
            }
          }
          (n && h & 64 && Ch(o), Zi(o, o.return));
          break;
        case 27:
          Mh(o);
        case 26:
        case 5:
          (An(a, o, n), n && l === null && h & 4 && Oh(o), Zi(o, o.return));
          break;
        case 12:
          An(a, o, n);
          break;
        case 31:
          (An(a, o, n), n && h & 4 && Uh(a, o));
          break;
        case 13:
          (An(a, o, n), n && h & 4 && Bh(a, o));
          break;
        case 22:
          (o.memoizedState === null && An(a, o, n), Zi(o, o.return));
          break;
        case 30:
          break;
        default:
          An(a, o, n);
      }
      e = e.sibling;
    }
  }
  function Oc(t, e) {
    var n = null;
    (t !== null &&
      t.memoizedState !== null &&
      t.memoizedState.cachePool !== null &&
      (n = t.memoizedState.cachePool.pool),
      (t = null),
      e.memoizedState !== null &&
        e.memoizedState.cachePool !== null &&
        (t = e.memoizedState.cachePool.pool),
      t !== n && (t != null && t.refCount++, n != null && wi(n)));
  }
  function Dc(t, e) {
    ((t = null),
      e.alternate !== null && (t = e.alternate.memoizedState.cache),
      (e = e.memoizedState.cache),
      e !== t && (e.refCount++, t != null && wi(t)));
  }
  function tn(t, e, n, l) {
    if (e.subtreeFlags & 10256)
      for (e = e.child; e !== null; ) (Lh(t, e, n, l), (e = e.sibling));
  }
  function Lh(t, e, n, l) {
    var a = e.flags;
    switch (e.tag) {
      case 0:
      case 11:
      case 15:
        (tn(t, e, n, l), a & 2048 && Vi(9, e));
        break;
      case 1:
        tn(t, e, n, l);
        break;
      case 3:
        (tn(t, e, n, l),
          a & 2048 &&
            ((t = null),
            e.alternate !== null && (t = e.alternate.memoizedState.cache),
            (e = e.memoizedState.cache),
            e !== t && (e.refCount++, t != null && wi(t))));
        break;
      case 12:
        if (a & 2048) {
          (tn(t, e, n, l), (t = e.stateNode));
          try {
            var o = e.memoizedProps,
              h = o.id,
              g = o.onPostCommit;
            typeof g == "function" &&
              g(
                h,
                e.alternate === null ? "mount" : "update",
                t.passiveEffectDuration,
                -0,
              );
          } catch (z) {
            Ht(e, e.return, z);
          }
        } else tn(t, e, n, l);
        break;
      case 31:
        tn(t, e, n, l);
        break;
      case 13:
        tn(t, e, n, l);
        break;
      case 23:
        break;
      case 22:
        ((o = e.stateNode),
          (h = e.alternate),
          e.memoizedState !== null
            ? o._visibility & 2
              ? tn(t, e, n, l)
              : Ki(t, e)
            : o._visibility & 2
              ? tn(t, e, n, l)
              : ((o._visibility |= 2),
                Wl(t, e, n, l, (e.subtreeFlags & 10256) !== 0 || !1)),
          a & 2048 && Oc(h, e));
        break;
      case 24:
        (tn(t, e, n, l), a & 2048 && Dc(e.alternate, e));
        break;
      default:
        tn(t, e, n, l);
    }
  }
  function Wl(t, e, n, l, a) {
    for (
      a = a && ((e.subtreeFlags & 10256) !== 0 || !1), e = e.child;
      e !== null;
    ) {
      var o = t,
        h = e,
        g = n,
        z = l,
        D = h.flags;
      switch (h.tag) {
        case 0:
        case 11:
        case 15:
          (Wl(o, h, g, z, a), Vi(8, h));
          break;
        case 23:
          break;
        case 22:
          var N = h.stateNode;
          (h.memoizedState !== null
            ? N._visibility & 2
              ? Wl(o, h, g, z, a)
              : Ki(o, h)
            : ((N._visibility |= 2), Wl(o, h, g, z, a)),
            a && D & 2048 && Oc(h.alternate, h));
          break;
        case 24:
          (Wl(o, h, g, z, a), a && D & 2048 && Dc(h.alternate, h));
          break;
        default:
          Wl(o, h, g, z, a);
      }
      e = e.sibling;
    }
  }
  function Ki(t, e) {
    if (e.subtreeFlags & 10256)
      for (e = e.child; e !== null; ) {
        var n = t,
          l = e,
          a = l.flags;
        switch (l.tag) {
          case 22:
            (Ki(n, l), a & 2048 && Oc(l.alternate, l));
            break;
          case 24:
            (Ki(n, l), a & 2048 && Dc(l.alternate, l));
            break;
          default:
            Ki(n, l);
        }
        e = e.sibling;
      }
  }
  var Ji = 8192;
  function $l(t, e, n) {
    if (t.subtreeFlags & Ji)
      for (t = t.child; t !== null; ) (qh(t, e, n), (t = t.sibling));
  }
  function qh(t, e, n) {
    switch (t.tag) {
      case 26:
        ($l(t, e, n),
          t.flags & Ji &&
            t.memoizedState !== null &&
            Hy(n, Pe, t.memoizedState, t.memoizedProps));
        break;
      case 5:
        $l(t, e, n);
        break;
      case 3:
      case 4:
        var l = Pe;
        ((Pe = Cu(t.stateNode.containerInfo)), $l(t, e, n), (Pe = l));
        break;
      case 22:
        t.memoizedState === null &&
          ((l = t.alternate),
          l !== null && l.memoizedState !== null
            ? ((l = Ji), (Ji = 16777216), $l(t, e, n), (Ji = l))
            : $l(t, e, n));
        break;
      default:
        $l(t, e, n);
    }
  }
  function Yh(t) {
    var e = t.alternate;
    if (e !== null && ((t = e.child), t !== null)) {
      e.child = null;
      do ((e = t.sibling), (t.sibling = null), (t = e));
      while (t !== null);
    }
  }
  function Fi(t) {
    var e = t.deletions;
    if ((t.flags & 16) !== 0) {
      if (e !== null)
        for (var n = 0; n < e.length; n++) {
          var l = e[n];
          ((re = l), Xh(l, t));
        }
      Yh(t);
    }
    if (t.subtreeFlags & 10256)
      for (t = t.child; t !== null; ) (Gh(t), (t = t.sibling));
  }
  function Gh(t) {
    switch (t.tag) {
      case 0:
      case 11:
      case 15:
        (Fi(t), t.flags & 2048 && Yn(9, t, t.return));
        break;
      case 3:
        Fi(t);
        break;
      case 12:
        Fi(t);
        break;
      case 22:
        var e = t.stateNode;
        t.memoizedState !== null &&
        e._visibility & 2 &&
        (t.return === null || t.return.tag !== 13)
          ? ((e._visibility &= -3), du(t))
          : Fi(t);
        break;
      default:
        Fi(t);
    }
  }
  function du(t) {
    var e = t.deletions;
    if ((t.flags & 16) !== 0) {
      if (e !== null)
        for (var n = 0; n < e.length; n++) {
          var l = e[n];
          ((re = l), Xh(l, t));
        }
      Yh(t);
    }
    for (t = t.child; t !== null; ) {
      switch (((e = t), e.tag)) {
        case 0:
        case 11:
        case 15:
          (Yn(8, e, e.return), du(e));
          break;
        case 22:
          ((n = e.stateNode),
            n._visibility & 2 && ((n._visibility &= -3), du(e)));
          break;
        default:
          du(e);
      }
      t = t.sibling;
    }
  }
  function Xh(t, e) {
    for (; re !== null; ) {
      var n = re;
      switch (n.tag) {
        case 0:
        case 11:
        case 15:
          Yn(8, n, e);
          break;
        case 23:
        case 22:
          if (n.memoizedState !== null && n.memoizedState.cachePool !== null) {
            var l = n.memoizedState.cachePool.pool;
            l != null && l.refCount++;
          }
          break;
        case 24:
          wi(n.memoizedState.cache);
      }
      if (((l = n.child), l !== null)) ((l.return = n), (re = l));
      else
        t: for (n = t; re !== null; ) {
          l = re;
          var a = l.sibling,
            o = l.return;
          if ((Nh(l), l === n)) {
            re = null;
            break t;
          }
          if (a !== null) {
            ((a.return = o), (re = a));
            break t;
          }
          re = o;
        }
    }
  }
  var Pg = {
      getCacheForType: function (t) {
        var e = fe(Pt),
          n = e.data.get(t);
        return (n === void 0 && ((n = t()), e.data.set(t, n)), n);
      },
      cacheSignal: function () {
        return fe(Pt).controller.signal;
      },
    },
    ty = typeof WeakMap == "function" ? WeakMap : Map,
    Rt = 0,
    Xt = null,
    At = null,
    Ot = 0,
    jt = 0,
    Ue = null,
    Gn = !1,
    Pl = !1,
    Mc = !1,
    Cn = 0,
    It = 0,
    Xn = 0,
    vl = 0,
    kc = 0,
    Be = 0,
    ti = 0,
    Ii = null,
    Ae = null,
    wc = !1,
    pu = 0,
    Qh = 0,
    mu = 1 / 0,
    gu = null,
    Qn = null,
    ae = 0,
    Vn = null,
    ei = null,
    _n = 0,
    Nc = 0,
    Rc = null,
    Vh = null,
    Wi = 0,
    Uc = null;
  function je() {
    return (Rt & 2) !== 0 && Ot !== 0 ? Ot & -Ot : M.T !== null ? Yc() : rf();
  }
  function Zh() {
    if (Be === 0)
      if ((Ot & 536870912) === 0 || Mt) {
        var t = Ta;
        ((Ta <<= 1), (Ta & 3932160) === 0 && (Ta = 262144), (Be = t));
      } else Be = 536870912;
    return ((t = Ne.current), t !== null && (t.flags |= 32), Be);
  }
  function Ce(t, e, n) {
    (((t === Xt && (jt === 2 || jt === 9)) || t.cancelPendingCommit !== null) &&
      (ni(t, 0), Zn(t, Ot, Be, !1)),
      bi(t, n),
      ((Rt & 2) === 0 || t !== Xt) &&
        (t === Xt &&
          ((Rt & 2) === 0 && (vl |= n), It === 4 && Zn(t, Ot, Be, !1)),
        an(t)));
  }
  function Kh(t, e, n) {
    if ((Rt & 6) !== 0) throw Error(c(327));
    var l = (!n && (e & 127) === 0 && (e & t.expiredLanes) === 0) || yi(t, e),
      a = l ? ly(t, e) : jc(t, e, !0),
      o = l;
    do {
      if (a === 0) {
        Pl && !l && Zn(t, e, 0, !1);
        break;
      } else {
        if (((n = t.current.alternate), o && !ey(n))) {
          ((a = jc(t, e, !1)), (o = !1));
          continue;
        }
        if (a === 2) {
          if (((o = e), t.errorRecoveryDisabledLanes & o)) var h = 0;
          else
            ((h = t.pendingLanes & -536870913),
              (h = h !== 0 ? h : h & 536870912 ? 536870912 : 0));
          if (h !== 0) {
            e = h;
            t: {
              var g = t;
              a = Ii;
              var z = g.current.memoizedState.isDehydrated;
              if ((z && (ni(g, h).flags |= 256), (h = jc(g, h, !1)), h !== 2)) {
                if (Mc && !z) {
                  ((g.errorRecoveryDisabledLanes |= o), (vl |= o), (a = 4));
                  break t;
                }
                ((o = Ae),
                  (Ae = a),
                  o !== null &&
                    (Ae === null ? (Ae = o) : Ae.push.apply(Ae, o)));
              }
              a = h;
            }
            if (((o = !1), a !== 2)) continue;
          }
        }
        if (a === 1) {
          (ni(t, 0), Zn(t, e, 0, !0));
          break;
        }
        t: {
          switch (((l = t), (o = a), o)) {
            case 0:
            case 1:
              throw Error(c(345));
            case 4:
              if ((e & 4194048) !== e) break;
            case 6:
              Zn(l, e, Be, !Gn);
              break t;
            case 2:
              Ae = null;
              break;
            case 3:
            case 5:
              break;
            default:
              throw Error(c(329));
          }
          if ((e & 62914560) === e && ((a = pu + 300 - ge()), 10 < a)) {
            if ((Zn(l, e, Be, !Gn), Ca(l, 0, !0) !== 0)) break t;
            ((_n = e),
              (l.timeoutHandle = Td(
                Jh.bind(
                  null,
                  l,
                  n,
                  Ae,
                  gu,
                  wc,
                  e,
                  Be,
                  vl,
                  ti,
                  Gn,
                  o,
                  "Throttled",
                  -0,
                  0,
                ),
                a,
              )));
            break t;
          }
          Jh(l, n, Ae, gu, wc, e, Be, vl, ti, Gn, o, null, -0, 0);
        }
      }
      break;
    } while (!0);
    an(t);
  }
  function Jh(t, e, n, l, a, o, h, g, z, D, N, q, k, w) {
    if (
      ((t.timeoutHandle = -1),
      (q = e.subtreeFlags),
      q & 8192 || (q & 16785408) === 16785408)
    ) {
      ((q = {
        stylesheets: null,
        count: 0,
        imgCount: 0,
        imgBytes: 0,
        suspenseyImages: [],
        waitingForImages: !0,
        waitingForViewTransition: !1,
        unsuspend: hn,
      }),
        qh(e, o, q));
      var et =
        (o & 62914560) === o ? pu - ge() : (o & 4194048) === o ? Qh - ge() : 0;
      if (((et = Ly(q, et)), et !== null)) {
        ((_n = o),
          (t.cancelPendingCommit = et(
            nd.bind(null, t, e, o, n, l, a, h, g, z, N, q, null, k, w),
          )),
          Zn(t, o, h, !D));
        return;
      }
    }
    nd(t, e, o, n, l, a, h, g, z);
  }
  function ey(t) {
    for (var e = t; ; ) {
      var n = e.tag;
      if (
        (n === 0 || n === 11 || n === 15) &&
        e.flags & 16384 &&
        ((n = e.updateQueue), n !== null && ((n = n.stores), n !== null))
      )
        for (var l = 0; l < n.length; l++) {
          var a = n[l],
            o = a.getSnapshot;
          a = a.value;
          try {
            if (!ke(o(), a)) return !1;
          } catch {
            return !1;
          }
        }
      if (((n = e.child), e.subtreeFlags & 16384 && n !== null))
        ((n.return = e), (e = n));
      else {
        if (e === t) break;
        for (; e.sibling === null; ) {
          if (e.return === null || e.return === t) return !0;
          e = e.return;
        }
        ((e.sibling.return = e.return), (e = e.sibling));
      }
    }
    return !0;
  }
  function Zn(t, e, n, l) {
    ((e &= ~kc),
      (e &= ~vl),
      (t.suspendedLanes |= e),
      (t.pingedLanes &= ~e),
      l && (t.warmLanes |= e),
      (l = t.expirationTimes));
    for (var a = e; 0 < a; ) {
      var o = 31 - Gt(a),
        h = 1 << o;
      ((l[o] = -1), (a &= ~h));
    }
    n !== 0 && lf(t, n, e);
  }
  function yu() {
    return (Rt & 6) === 0 ? ($i(0), !1) : !0;
  }
  function Bc() {
    if (At !== null) {
      if (jt === 0) var t = At.return;
      else ((t = At), (gn = fl = null), $r(t), (Zl = null), (Ri = 0), (t = At));
      for (; t !== null; ) (Ah(t.alternate, t), (t = t.return));
      At = null;
    }
  }
  function ni(t, e) {
    var n = t.timeoutHandle;
    (n !== -1 && ((t.timeoutHandle = -1), xy(n)),
      (n = t.cancelPendingCommit),
      n !== null && ((t.cancelPendingCommit = null), n()),
      (_n = 0),
      Bc(),
      (Xt = t),
      (At = n = pn(t.current, null)),
      (Ot = e),
      (jt = 0),
      (Ue = null),
      (Gn = !1),
      (Pl = yi(t, e)),
      (Mc = !1),
      (ti = Be = kc = vl = Xn = It = 0),
      (Ae = Ii = null),
      (wc = !1),
      (e & 8) !== 0 && (e |= e & 32));
    var l = t.entangledLanes;
    if (l !== 0)
      for (t = t.entanglements, l &= e; 0 < l; ) {
        var a = 31 - Gt(l),
          o = 1 << a;
        ((e |= t[a]), (l &= ~o));
      }
    return ((Cn = e), Ha(), n);
  }
  function Fh(t, e) {
    ((gt = null),
      (M.H = Gi),
      e === Vl || e === Za
        ? ((e = ss()), (jt = 3))
        : e === qr
          ? ((e = ss()), (jt = 4))
          : (jt =
              e === pc
                ? 8
                : e !== null &&
                    typeof e == "object" &&
                    typeof e.then == "function"
                  ? 6
                  : 1),
      (Ue = e),
      At === null && ((It = 1), uu(t, Xe(e, t.current))));
  }
  function Ih() {
    var t = Ne.current;
    return t === null
      ? !0
      : (Ot & 4194048) === Ot
        ? Ke === null
        : (Ot & 62914560) === Ot || (Ot & 536870912) !== 0
          ? t === Ke
          : !1;
  }
  function Wh() {
    var t = M.H;
    return ((M.H = Gi), t === null ? Gi : t);
  }
  function $h() {
    var t = M.A;
    return ((M.A = Pg), t);
  }
  function bu() {
    ((It = 4),
      Gn || ((Ot & 4194048) !== Ot && Ne.current !== null) || (Pl = !0),
      ((Xn & 134217727) === 0 && (vl & 134217727) === 0) ||
        Xt === null ||
        Zn(Xt, Ot, Be, !1));
  }
  function jc(t, e, n) {
    var l = Rt;
    Rt |= 2;
    var a = Wh(),
      o = $h();
    ((Xt !== t || Ot !== e) && ((gu = null), ni(t, e)), (e = !1));
    var h = It;
    t: do
      try {
        if (jt !== 0 && At !== null) {
          var g = At,
            z = Ue;
          switch (jt) {
            case 8:
              (Bc(), (h = 6));
              break t;
            case 3:
            case 2:
            case 9:
            case 6:
              Ne.current === null && (e = !0);
              var D = jt;
              if (((jt = 0), (Ue = null), li(t, g, z, D), n && Pl)) {
                h = 0;
                break t;
              }
              break;
            default:
              ((D = jt), (jt = 0), (Ue = null), li(t, g, z, D));
          }
        }
        (ny(), (h = It));
        break;
      } catch (N) {
        Fh(t, N);
      }
    while (!0);
    return (
      e && t.shellSuspendCounter++,
      (gn = fl = null),
      (Rt = l),
      (M.H = a),
      (M.A = o),
      At === null && ((Xt = null), (Ot = 0), Ha()),
      h
    );
  }
  function ny() {
    for (; At !== null; ) Ph(At);
  }
  function ly(t, e) {
    var n = Rt;
    Rt |= 2;
    var l = Wh(),
      a = $h();
    Xt !== t || Ot !== e
      ? ((gu = null), (mu = ge() + 500), ni(t, e))
      : (Pl = yi(t, e));
    t: do
      try {
        if (jt !== 0 && At !== null) {
          e = At;
          var o = Ue;
          e: switch (jt) {
            case 1:
              ((jt = 0), (Ue = null), li(t, e, o, 1));
              break;
            case 2:
            case 9:
              if (os(o)) {
                ((jt = 0), (Ue = null), td(e));
                break;
              }
              ((e = function () {
                ((jt !== 2 && jt !== 9) || Xt !== t || (jt = 7), an(t));
              }),
                o.then(e, e));
              break t;
            case 3:
              jt = 7;
              break t;
            case 4:
              jt = 5;
              break t;
            case 7:
              os(o)
                ? ((jt = 0), (Ue = null), td(e))
                : ((jt = 0), (Ue = null), li(t, e, o, 7));
              break;
            case 5:
              var h = null;
              switch (At.tag) {
                case 26:
                  h = At.memoizedState;
                case 5:
                case 27:
                  var g = At;
                  if (h ? Ld(h) : g.stateNode.complete) {
                    ((jt = 0), (Ue = null));
                    var z = g.sibling;
                    if (z !== null) At = z;
                    else {
                      var D = g.return;
                      D !== null ? ((At = D), vu(D)) : (At = null);
                    }
                    break e;
                  }
              }
              ((jt = 0), (Ue = null), li(t, e, o, 5));
              break;
            case 6:
              ((jt = 0), (Ue = null), li(t, e, o, 6));
              break;
            case 8:
              (Bc(), (It = 6));
              break t;
            default:
              throw Error(c(462));
          }
        }
        iy();
        break;
      } catch (N) {
        Fh(t, N);
      }
    while (!0);
    return (
      (gn = fl = null),
      (M.H = l),
      (M.A = a),
      (Rt = n),
      At !== null ? 0 : ((Xt = null), (Ot = 0), Ha(), It)
    );
  }
  function iy() {
    for (; At !== null && !Iu(); ) Ph(At);
  }
  function Ph(t) {
    var e = zh(t.alternate, t, Cn);
    ((t.memoizedProps = t.pendingProps), e === null ? vu(t) : (At = e));
  }
  function td(t) {
    var e = t,
      n = e.alternate;
    switch (e.tag) {
      case 15:
      case 0:
        e = yh(n, e, e.pendingProps, e.type, void 0, Ot);
        break;
      case 11:
        e = yh(n, e, e.pendingProps, e.type.render, e.ref, Ot);
        break;
      case 5:
        $r(e);
      default:
        (Ah(n, e), (e = At = $f(e, Cn)), (e = zh(n, e, Cn)));
    }
    ((t.memoizedProps = t.pendingProps), e === null ? vu(t) : (At = e));
  }
  function li(t, e, n, l) {
    ((gn = fl = null), $r(e), (Zl = null), (Ri = 0));
    var a = e.return;
    try {
      if (Zg(t, a, e, n, Ot)) {
        ((It = 1), uu(t, Xe(n, t.current)), (At = null));
        return;
      }
    } catch (o) {
      if (a !== null) throw ((At = a), o);
      ((It = 1), uu(t, Xe(n, t.current)), (At = null));
      return;
    }
    e.flags & 32768
      ? (Mt || l === 1
          ? (t = !0)
          : Pl || (Ot & 536870912) !== 0
            ? (t = !1)
            : ((Gn = t = !0),
              (l === 2 || l === 9 || l === 3 || l === 6) &&
                ((l = Ne.current),
                l !== null && l.tag === 13 && (l.flags |= 16384))),
        ed(e, t))
      : vu(e);
  }
  function vu(t) {
    var e = t;
    do {
      if ((e.flags & 32768) !== 0) {
        ed(e, Gn);
        return;
      }
      t = e.return;
      var n = Fg(e.alternate, e, Cn);
      if (n !== null) {
        At = n;
        return;
      }
      if (((e = e.sibling), e !== null)) {
        At = e;
        return;
      }
      At = e = t;
    } while (e !== null);
    It === 0 && (It = 5);
  }
  function ed(t, e) {
    do {
      var n = Ig(t.alternate, t);
      if (n !== null) {
        ((n.flags &= 32767), (At = n));
        return;
      }
      if (
        ((n = t.return),
        n !== null &&
          ((n.flags |= 32768), (n.subtreeFlags = 0), (n.deletions = null)),
        !e && ((t = t.sibling), t !== null))
      ) {
        At = t;
        return;
      }
      At = t = n;
    } while (t !== null);
    ((It = 6), (At = null));
  }
  function nd(t, e, n, l, a, o, h, g, z) {
    t.cancelPendingCommit = null;
    do Su();
    while (ae !== 0);
    if ((Rt & 6) !== 0) throw Error(c(327));
    if (e !== null) {
      if (e === t.current) throw Error(c(177));
      if (
        ((o = e.lanes | e.childLanes),
        (o |= Ar),
        jm(t, n, o, h, g, z),
        t === Xt && ((At = Xt = null), (Ot = 0)),
        (ei = e),
        (Vn = t),
        (_n = n),
        (Nc = o),
        (Rc = a),
        (Vh = l),
        (e.subtreeFlags & 10256) !== 0 || (e.flags & 10256) !== 0
          ? ((t.callbackNode = null),
            (t.callbackPriority = 0),
            cy(ft, function () {
              return (rd(), null);
            }))
          : ((t.callbackNode = null), (t.callbackPriority = 0)),
        (l = (e.flags & 13878) !== 0),
        (e.subtreeFlags & 13878) !== 0 || l)
      ) {
        ((l = M.T), (M.T = null), (a = B.p), (B.p = 2), (h = Rt), (Rt |= 4));
        try {
          Wg(t, e, n);
        } finally {
          ((Rt = h), (B.p = a), (M.T = l));
        }
      }
      ((ae = 1), ld(), id(), ad());
    }
  }
  function ld() {
    if (ae === 1) {
      ae = 0;
      var t = Vn,
        e = ei,
        n = (e.flags & 13878) !== 0;
      if ((e.subtreeFlags & 13878) !== 0 || n) {
        ((n = M.T), (M.T = null));
        var l = B.p;
        B.p = 2;
        var a = Rt;
        Rt |= 4;
        try {
          jh(e, t);
          var o = Fc,
            h = Xf(t.containerInfo),
            g = o.focusedElem,
            z = o.selectionRange;
          if (
            h !== g &&
            g &&
            g.ownerDocument &&
            Gf(g.ownerDocument.documentElement, g)
          ) {
            if (z !== null && Sr(g)) {
              var D = z.start,
                N = z.end;
              if ((N === void 0 && (N = D), "selectionStart" in g))
                ((g.selectionStart = D),
                  (g.selectionEnd = Math.min(N, g.value.length)));
              else {
                var q = g.ownerDocument || document,
                  k = (q && q.defaultView) || window;
                if (k.getSelection) {
                  var w = k.getSelection(),
                    et = g.textContent.length,
                    ot = Math.min(z.start, et),
                    Yt = z.end === void 0 ? ot : Math.min(z.end, et);
                  !w.extend && ot > Yt && ((h = Yt), (Yt = ot), (ot = h));
                  var _ = Yf(g, ot),
                    C = Yf(g, Yt);
                  if (
                    _ &&
                    C &&
                    (w.rangeCount !== 1 ||
                      w.anchorNode !== _.node ||
                      w.anchorOffset !== _.offset ||
                      w.focusNode !== C.node ||
                      w.focusOffset !== C.offset)
                  ) {
                    var O = q.createRange();
                    (O.setStart(_.node, _.offset),
                      w.removeAllRanges(),
                      ot > Yt
                        ? (w.addRange(O), w.extend(C.node, C.offset))
                        : (O.setEnd(C.node, C.offset), w.addRange(O)));
                  }
                }
              }
            }
            for (q = [], w = g; (w = w.parentNode); )
              w.nodeType === 1 &&
                q.push({ element: w, left: w.scrollLeft, top: w.scrollTop });
            for (
              typeof g.focus == "function" && g.focus(), g = 0;
              g < q.length;
              g++
            ) {
              var L = q[g];
              ((L.element.scrollLeft = L.left), (L.element.scrollTop = L.top));
            }
          }
          ((wu = !!Jc), (Fc = Jc = null));
        } finally {
          ((Rt = a), (B.p = l), (M.T = n));
        }
      }
      ((t.current = e), (ae = 2));
    }
  }
  function id() {
    if (ae === 2) {
      ae = 0;
      var t = Vn,
        e = ei,
        n = (e.flags & 8772) !== 0;
      if ((e.subtreeFlags & 8772) !== 0 || n) {
        ((n = M.T), (M.T = null));
        var l = B.p;
        B.p = 2;
        var a = Rt;
        Rt |= 4;
        try {
          wh(t, e.alternate, e);
        } finally {
          ((Rt = a), (B.p = l), (M.T = n));
        }
      }
      ae = 3;
    }
  }
  function ad() {
    if (ae === 4 || ae === 3) {
      ((ae = 0), Wu());
      var t = Vn,
        e = ei,
        n = _n,
        l = Vh;
      (e.subtreeFlags & 10256) !== 0 || (e.flags & 10256) !== 0
        ? (ae = 5)
        : ((ae = 0), (ei = Vn = null), ud(t, t.pendingLanes));
      var a = t.pendingLanes;
      if (
        (a === 0 && (Qn = null),
        er(n),
        (e = e.stateNode),
        ie && typeof ie.onCommitFiberRoot == "function")
      )
        try {
          ie.onCommitFiberRoot(ye, e, void 0, (e.current.flags & 128) === 128);
        } catch {}
      if (l !== null) {
        ((e = M.T), (a = B.p), (B.p = 2), (M.T = null));
        try {
          for (var o = t.onRecoverableError, h = 0; h < l.length; h++) {
            var g = l[h];
            o(g.value, { componentStack: g.stack });
          }
        } finally {
          ((M.T = e), (B.p = a));
        }
      }
      ((_n & 3) !== 0 && Su(),
        an(t),
        (a = t.pendingLanes),
        (n & 261930) !== 0 && (a & 42) !== 0
          ? t === Uc
            ? Wi++
            : ((Wi = 0), (Uc = t))
          : (Wi = 0),
        $i(0));
    }
  }
  function ud(t, e) {
    (t.pooledCacheLanes &= e) === 0 &&
      ((e = t.pooledCache), e != null && ((t.pooledCache = null), wi(e)));
  }
  function Su() {
    return (ld(), id(), ad(), rd());
  }
  function rd() {
    if (ae !== 5) return !1;
    var t = Vn,
      e = Nc;
    Nc = 0;
    var n = er(_n),
      l = M.T,
      a = B.p;
    try {
      ((B.p = 32 > n ? 32 : n), (M.T = null), (n = Rc), (Rc = null));
      var o = Vn,
        h = _n;
      if (((ae = 0), (ei = Vn = null), (_n = 0), (Rt & 6) !== 0))
        throw Error(c(331));
      var g = Rt;
      if (
        ((Rt |= 4),
        Gh(o.current),
        Lh(o, o.current, h, n),
        (Rt = g),
        $i(0, !1),
        ie && typeof ie.onPostCommitFiberRoot == "function")
      )
        try {
          ie.onPostCommitFiberRoot(ye, o);
        } catch {}
      return !0;
    } finally {
      ((B.p = a), (M.T = l), ud(t, e));
    }
  }
  function cd(t, e, n) {
    ((e = Xe(n, e)),
      (e = dc(t.stateNode, e, 2)),
      (t = Hn(t, e, 2)),
      t !== null && (bi(t, 2), an(t)));
  }
  function Ht(t, e, n) {
    if (t.tag === 3) cd(t, t, n);
    else
      for (; e !== null; ) {
        if (e.tag === 3) {
          cd(e, t, n);
          break;
        } else if (e.tag === 1) {
          var l = e.stateNode;
          if (
            typeof e.type.getDerivedStateFromError == "function" ||
            (typeof l.componentDidCatch == "function" &&
              (Qn === null || !Qn.has(l)))
          ) {
            ((t = Xe(n, t)),
              (n = oh(2)),
              (l = Hn(e, n, 2)),
              l !== null && (fh(n, l, e, t), bi(l, 2), an(l)));
            break;
          }
        }
        e = e.return;
      }
  }
  function Hc(t, e, n) {
    var l = t.pingCache;
    if (l === null) {
      l = t.pingCache = new ty();
      var a = new Set();
      l.set(e, a);
    } else ((a = l.get(e)), a === void 0 && ((a = new Set()), l.set(e, a)));
    a.has(n) ||
      ((Mc = !0), a.add(n), (t = ay.bind(null, t, e, n)), e.then(t, t));
  }
  function ay(t, e, n) {
    var l = t.pingCache;
    (l !== null && l.delete(e),
      (t.pingedLanes |= t.suspendedLanes & n),
      (t.warmLanes &= ~n),
      Xt === t &&
        (Ot & n) === n &&
        (It === 4 || (It === 3 && (Ot & 62914560) === Ot && 300 > ge() - pu)
          ? (Rt & 2) === 0 && ni(t, 0)
          : (kc |= n),
        ti === Ot && (ti = 0)),
      an(t));
  }
  function od(t, e) {
    (e === 0 && (e = nf()), (t = rl(t, e)), t !== null && (bi(t, e), an(t)));
  }
  function uy(t) {
    var e = t.memoizedState,
      n = 0;
    (e !== null && (n = e.retryLane), od(t, n));
  }
  function ry(t, e) {
    var n = 0;
    switch (t.tag) {
      case 31:
      case 13:
        var l = t.stateNode,
          a = t.memoizedState;
        a !== null && (n = a.retryLane);
        break;
      case 19:
        l = t.stateNode;
        break;
      case 22:
        l = t.stateNode._retryCache;
        break;
      default:
        throw Error(c(314));
    }
    (l !== null && l.delete(e), od(t, n));
  }
  function cy(t, e) {
    return Tl(t, e);
  }
  var xu = null,
    ii = null,
    Lc = !1,
    Eu = !1,
    qc = !1,
    Kn = 0;
  function an(t) {
    (t !== ii &&
      t.next === null &&
      (ii === null ? (xu = ii = t) : (ii = ii.next = t)),
      (Eu = !0),
      Lc || ((Lc = !0), fy()));
  }
  function $i(t, e) {
    if (!qc && Eu) {
      qc = !0;
      do
        for (var n = !1, l = xu; l !== null; ) {
          if (t !== 0) {
            var a = l.pendingLanes;
            if (a === 0) var o = 0;
            else {
              var h = l.suspendedLanes,
                g = l.pingedLanes;
              ((o = (1 << (31 - Gt(42 | t) + 1)) - 1),
                (o &= a & ~(h & ~g)),
                (o = o & 201326741 ? (o & 201326741) | 1 : o ? o | 2 : 0));
            }
            o !== 0 && ((n = !0), dd(l, o));
          } else
            ((o = Ot),
              (o = Ca(
                l,
                l === Xt ? o : 0,
                l.cancelPendingCommit !== null || l.timeoutHandle !== -1,
              )),
              (o & 3) === 0 || yi(l, o) || ((n = !0), dd(l, o)));
          l = l.next;
        }
      while (n);
      qc = !1;
    }
  }
  function oy() {
    fd();
  }
  function fd() {
    Eu = Lc = !1;
    var t = 0;
    Kn !== 0 && Sy() && (t = Kn);
    for (var e = ge(), n = null, l = xu; l !== null; ) {
      var a = l.next,
        o = sd(l, e);
      (o === 0
        ? ((l.next = null),
          n === null ? (xu = a) : (n.next = a),
          a === null && (ii = n))
        : ((n = l), (t !== 0 || (o & 3) !== 0) && (Eu = !0)),
        (l = a));
    }
    ((ae !== 0 && ae !== 5) || $i(t), Kn !== 0 && (Kn = 0));
  }
  function sd(t, e) {
    for (
      var n = t.suspendedLanes,
        l = t.pingedLanes,
        a = t.expirationTimes,
        o = t.pendingLanes & -62914561;
      0 < o;
    ) {
      var h = 31 - Gt(o),
        g = 1 << h,
        z = a[h];
      (z === -1
        ? ((g & n) === 0 || (g & l) !== 0) && (a[h] = Bm(g, e))
        : z <= e && (t.expiredLanes |= g),
        (o &= ~g));
    }
    if (
      ((e = Xt),
      (n = Ot),
      (n = Ca(
        t,
        t === e ? n : 0,
        t.cancelPendingCommit !== null || t.timeoutHandle !== -1,
      )),
      (l = t.callbackNode),
      n === 0 ||
        (t === e && (jt === 2 || jt === 9)) ||
        t.cancelPendingCommit !== null)
    )
      return (
        l !== null && l !== null && gi(l),
        (t.callbackNode = null),
        (t.callbackPriority = 0)
      );
    if ((n & 3) === 0 || yi(t, n)) {
      if (((e = n & -n), e === t.callbackPriority)) return e;
      switch ((l !== null && gi(l), er(n))) {
        case 2:
        case 8:
          n = J;
          break;
        case 32:
          n = ft;
          break;
        case 268435456:
          n = Bt;
          break;
        default:
          n = ft;
      }
      return (
        (l = hd.bind(null, t)),
        (n = Tl(n, l)),
        (t.callbackPriority = e),
        (t.callbackNode = n),
        e
      );
    }
    return (
      l !== null && l !== null && gi(l),
      (t.callbackPriority = 2),
      (t.callbackNode = null),
      2
    );
  }
  function hd(t, e) {
    if (ae !== 0 && ae !== 5)
      return ((t.callbackNode = null), (t.callbackPriority = 0), null);
    var n = t.callbackNode;
    if (Su() && t.callbackNode !== n) return null;
    var l = Ot;
    return (
      (l = Ca(
        t,
        t === Xt ? l : 0,
        t.cancelPendingCommit !== null || t.timeoutHandle !== -1,
      )),
      l === 0
        ? null
        : (Kh(t, l, e),
          sd(t, ge()),
          t.callbackNode != null && t.callbackNode === n
            ? hd.bind(null, t)
            : null)
    );
  }
  function dd(t, e) {
    if (Su()) return null;
    Kh(t, e, !0);
  }
  function fy() {
    Ey(function () {
      (Rt & 6) !== 0 ? Tl(j, oy) : fd();
    });
  }
  function Yc() {
    if (Kn === 0) {
      var t = Xl;
      (t === 0 && ((t = za), (za <<= 1), (za & 261888) === 0 && (za = 256)),
        (Kn = t));
    }
    return Kn;
  }
  function pd(t) {
    return t == null || typeof t == "symbol" || typeof t == "boolean"
      ? null
      : typeof t == "function"
        ? t
        : Ma("" + t);
  }
  function md(t, e) {
    var n = e.ownerDocument.createElement("input");
    return (
      (n.name = e.name),
      (n.value = e.value),
      t.id && n.setAttribute("form", t.id),
      e.parentNode.insertBefore(n, e),
      (t = new FormData(t)),
      n.parentNode.removeChild(n),
      t
    );
  }
  function sy(t, e, n, l, a) {
    if (e === "submit" && n && n.stateNode === a) {
      var o = pd((a[Se] || null).action),
        h = l.submitter;
      h &&
        ((e = (e = h[Se] || null)
          ? pd(e.formAction)
          : h.getAttribute("formAction")),
        e !== null && ((o = e), (h = null)));
      var g = new Ra("action", "action", null, l, a);
      t.push({
        event: g,
        listeners: [
          {
            instance: null,
            listener: function () {
              if (l.defaultPrevented) {
                if (Kn !== 0) {
                  var z = h ? md(a, h) : new FormData(a);
                  rc(
                    n,
                    { pending: !0, data: z, method: a.method, action: o },
                    null,
                    z,
                  );
                }
              } else
                typeof o == "function" &&
                  (g.preventDefault(),
                  (z = h ? md(a, h) : new FormData(a)),
                  rc(
                    n,
                    { pending: !0, data: z, method: a.method, action: o },
                    o,
                    z,
                  ));
            },
            currentTarget: a,
          },
        ],
      });
    }
  }
  for (var Gc = 0; Gc < Tr.length; Gc++) {
    var Xc = Tr[Gc],
      hy = Xc.toLowerCase(),
      dy = Xc[0].toUpperCase() + Xc.slice(1);
    $e(hy, "on" + dy);
  }
  ($e(Zf, "onAnimationEnd"),
    $e(Kf, "onAnimationIteration"),
    $e(Jf, "onAnimationStart"),
    $e("dblclick", "onDoubleClick"),
    $e("focusin", "onFocus"),
    $e("focusout", "onBlur"),
    $e(Dg, "onTransitionRun"),
    $e(Mg, "onTransitionStart"),
    $e(kg, "onTransitionCancel"),
    $e(Ff, "onTransitionEnd"),
    Dl("onMouseEnter", ["mouseout", "mouseover"]),
    Dl("onMouseLeave", ["mouseout", "mouseover"]),
    Dl("onPointerEnter", ["pointerout", "pointerover"]),
    Dl("onPointerLeave", ["pointerout", "pointerover"]),
    ll(
      "onChange",
      "change click focusin focusout input keydown keyup selectionchange".split(
        " ",
      ),
    ),
    ll(
      "onSelect",
      "focusout contextmenu dragend focusin keydown keyup mousedown mouseup selectionchange".split(
        " ",
      ),
    ),
    ll("onBeforeInput", ["compositionend", "keypress", "textInput", "paste"]),
    ll(
      "onCompositionEnd",
      "compositionend focusout keydown keypress keyup mousedown".split(" "),
    ),
    ll(
      "onCompositionStart",
      "compositionstart focusout keydown keypress keyup mousedown".split(" "),
    ),
    ll(
      "onCompositionUpdate",
      "compositionupdate focusout keydown keypress keyup mousedown".split(" "),
    ));
  var Pi =
      "abort canplay canplaythrough durationchange emptied encrypted ended error loadeddata loadedmetadata loadstart pause play playing progress ratechange resize seeked seeking stalled suspend timeupdate volumechange waiting".split(
        " ",
      ),
    py = new Set(
      "beforetoggle cancel close invalid load scroll scrollend toggle"
        .split(" ")
        .concat(Pi),
    );
  function gd(t, e) {
    e = (e & 4) !== 0;
    for (var n = 0; n < t.length; n++) {
      var l = t[n],
        a = l.event;
      l = l.listeners;
      t: {
        var o = void 0;
        if (e)
          for (var h = l.length - 1; 0 <= h; h--) {
            var g = l[h],
              z = g.instance,
              D = g.currentTarget;
            if (((g = g.listener), z !== o && a.isPropagationStopped()))
              break t;
            ((o = g), (a.currentTarget = D));
            try {
              o(a);
            } catch (N) {
              ja(N);
            }
            ((a.currentTarget = null), (o = z));
          }
        else
          for (h = 0; h < l.length; h++) {
            if (
              ((g = l[h]),
              (z = g.instance),
              (D = g.currentTarget),
              (g = g.listener),
              z !== o && a.isPropagationStopped())
            )
              break t;
            ((o = g), (a.currentTarget = D));
            try {
              o(a);
            } catch (N) {
              ja(N);
            }
            ((a.currentTarget = null), (o = z));
          }
      }
    }
  }
  function Ct(t, e) {
    var n = e[nr];
    n === void 0 && (n = e[nr] = new Set());
    var l = t + "__bubble";
    n.has(l) || (yd(e, t, 2, !1), n.add(l));
  }
  function Qc(t, e, n) {
    var l = 0;
    (e && (l |= 4), yd(n, t, l, e));
  }
  var zu = "_reactListening" + Math.random().toString(36).slice(2);
  function Vc(t) {
    if (!t[zu]) {
      ((t[zu] = !0),
        ff.forEach(function (n) {
          n !== "selectionchange" && (py.has(n) || Qc(n, !1, t), Qc(n, !0, t));
        }));
      var e = t.nodeType === 9 ? t : t.ownerDocument;
      e === null || e[zu] || ((e[zu] = !0), Qc("selectionchange", !1, e));
    }
  }
  function yd(t, e, n, l) {
    switch (Zd(e)) {
      case 2:
        var a = Gy;
        break;
      case 8:
        a = Xy;
        break;
      default:
        a = uo;
    }
    ((n = a.bind(null, e, n, t)),
      (a = void 0),
      !sr ||
        (e !== "touchstart" && e !== "touchmove" && e !== "wheel") ||
        (a = !0),
      l
        ? a !== void 0
          ? t.addEventListener(e, n, { capture: !0, passive: a })
          : t.addEventListener(e, n, !0)
        : a !== void 0
          ? t.addEventListener(e, n, { passive: a })
          : t.addEventListener(e, n, !1));
  }
  function Zc(t, e, n, l, a) {
    var o = l;
    if ((e & 1) === 0 && (e & 2) === 0 && l !== null)
      t: for (;;) {
        if (l === null) return;
        var h = l.tag;
        if (h === 3 || h === 4) {
          var g = l.stateNode.containerInfo;
          if (g === a) break;
          if (h === 4)
            for (h = l.return; h !== null; ) {
              var z = h.tag;
              if ((z === 3 || z === 4) && h.stateNode.containerInfo === a)
                return;
              h = h.return;
            }
          for (; g !== null; ) {
            if (((h = Cl(g)), h === null)) return;
            if (((z = h.tag), z === 5 || z === 6 || z === 26 || z === 27)) {
              l = o = h;
              continue t;
            }
            g = g.parentNode;
          }
        }
        l = l.return;
      }
    Ef(function () {
      var D = o,
        N = or(n),
        q = [];
      t: {
        var k = If.get(t);
        if (k !== void 0) {
          var w = Ra,
            et = t;
          switch (t) {
            case "keypress":
              if (wa(n) === 0) break t;
            case "keydown":
            case "keyup":
              w = rg;
              break;
            case "focusin":
              ((et = "focus"), (w = mr));
              break;
            case "focusout":
              ((et = "blur"), (w = mr));
              break;
            case "beforeblur":
            case "afterblur":
              w = mr;
              break;
            case "click":
              if (n.button === 2) break t;
            case "auxclick":
            case "dblclick":
            case "mousedown":
            case "mousemove":
            case "mouseup":
            case "mouseout":
            case "mouseover":
            case "contextmenu":
              w = Af;
              break;
            case "drag":
            case "dragend":
            case "dragenter":
            case "dragexit":
            case "dragleave":
            case "dragover":
            case "dragstart":
            case "drop":
              w = Fm;
              break;
            case "touchcancel":
            case "touchend":
            case "touchmove":
            case "touchstart":
              w = fg;
              break;
            case Zf:
            case Kf:
            case Jf:
              w = $m;
              break;
            case Ff:
              w = hg;
              break;
            case "scroll":
            case "scrollend":
              w = Km;
              break;
            case "wheel":
              w = pg;
              break;
            case "copy":
            case "cut":
            case "paste":
              w = tg;
              break;
            case "gotpointercapture":
            case "lostpointercapture":
            case "pointercancel":
            case "pointerdown":
            case "pointermove":
            case "pointerout":
            case "pointerover":
            case "pointerup":
              w = _f;
              break;
            case "toggle":
            case "beforetoggle":
              w = gg;
          }
          var ot = (e & 4) !== 0,
            Yt = !ot && (t === "scroll" || t === "scrollend"),
            _ = ot ? (k !== null ? k + "Capture" : null) : k;
          ot = [];
          for (var C = D, O; C !== null; ) {
            var L = C;
            if (
              ((O = L.stateNode),
              (L = L.tag),
              (L !== 5 && L !== 26 && L !== 27) ||
                O === null ||
                _ === null ||
                ((L = xi(C, _)), L != null && ot.push(ta(C, L, O))),
              Yt)
            )
              break;
            C = C.return;
          }
          0 < ot.length &&
            ((k = new w(k, et, null, n, N)),
            q.push({ event: k, listeners: ot }));
        }
      }
      if ((e & 7) === 0) {
        t: {
          if (
            ((k = t === "mouseover" || t === "pointerover"),
            (w = t === "mouseout" || t === "pointerout"),
            k &&
              n !== cr &&
              (et = n.relatedTarget || n.fromElement) &&
              (Cl(et) || et[Al]))
          )
            break t;
          if (
            (w || k) &&
            ((k =
              N.window === N
                ? N
                : (k = N.ownerDocument)
                  ? k.defaultView || k.parentWindow
                  : window),
            w
              ? ((et = n.relatedTarget || n.toElement),
                (w = D),
                (et = et ? Cl(et) : null),
                et !== null &&
                  ((Yt = s(et)),
                  (ot = et.tag),
                  et !== Yt || (ot !== 5 && ot !== 27 && ot !== 6)) &&
                  (et = null))
              : ((w = null), (et = D)),
            w !== et)
          ) {
            if (
              ((ot = Af),
              (L = "onMouseLeave"),
              (_ = "onMouseEnter"),
              (C = "mouse"),
              (t === "pointerout" || t === "pointerover") &&
                ((ot = _f),
                (L = "onPointerLeave"),
                (_ = "onPointerEnter"),
                (C = "pointer")),
              (Yt = w == null ? k : Si(w)),
              (O = et == null ? k : Si(et)),
              (k = new ot(L, C + "leave", w, n, N)),
              (k.target = Yt),
              (k.relatedTarget = O),
              (L = null),
              Cl(N) === D &&
                ((ot = new ot(_, C + "enter", et, n, N)),
                (ot.target = O),
                (ot.relatedTarget = Yt),
                (L = ot)),
              (Yt = L),
              w && et)
            )
              e: {
                for (ot = my, _ = w, C = et, O = 0, L = _; L; L = ot(L)) O++;
                L = 0;
                for (var rt = C; rt; rt = ot(rt)) L++;
                for (; 0 < O - L; ) ((_ = ot(_)), O--);
                for (; 0 < L - O; ) ((C = ot(C)), L--);
                for (; O--; ) {
                  if (_ === C || (C !== null && _ === C.alternate)) {
                    ot = _;
                    break e;
                  }
                  ((_ = ot(_)), (C = ot(C)));
                }
                ot = null;
              }
            else ot = null;
            (w !== null && bd(q, k, w, ot, !1),
              et !== null && Yt !== null && bd(q, Yt, et, ot, !0));
          }
        }
        t: {
          if (
            ((k = D ? Si(D) : window),
            (w = k.nodeName && k.nodeName.toLowerCase()),
            w === "select" || (w === "input" && k.type === "file"))
          )
            var wt = Uf;
          else if (Nf(k))
            if (Bf) wt = Cg;
            else {
              wt = Tg;
              var nt = zg;
            }
          else
            ((w = k.nodeName),
              !w ||
              w.toLowerCase() !== "input" ||
              (k.type !== "checkbox" && k.type !== "radio")
                ? D && rr(D.elementType) && (wt = Uf)
                : (wt = Ag));
          if (wt && (wt = wt(t, D))) {
            Rf(q, wt, n, N);
            break t;
          }
          (nt && nt(t, k, D),
            t === "focusout" &&
              D &&
              k.type === "number" &&
              D.memoizedProps.value != null &&
              ur(k, "number", k.value));
        }
        switch (((nt = D ? Si(D) : window), t)) {
          case "focusin":
            (Nf(nt) || nt.contentEditable === "true") &&
              ((Ul = nt), (xr = D), (Di = null));
            break;
          case "focusout":
            Di = xr = Ul = null;
            break;
          case "mousedown":
            Er = !0;
            break;
          case "contextmenu":
          case "mouseup":
          case "dragend":
            ((Er = !1), Qf(q, n, N));
            break;
          case "selectionchange":
            if (Og) break;
          case "keydown":
          case "keyup":
            Qf(q, n, N);
        }
        var bt;
        if (yr)
          t: {
            switch (t) {
              case "compositionstart":
                var Dt = "onCompositionStart";
                break t;
              case "compositionend":
                Dt = "onCompositionEnd";
                break t;
              case "compositionupdate":
                Dt = "onCompositionUpdate";
                break t;
            }
            Dt = void 0;
          }
        else
          Rl
            ? kf(t, n) && (Dt = "onCompositionEnd")
            : t === "keydown" &&
              n.keyCode === 229 &&
              (Dt = "onCompositionStart");
        (Dt &&
          (Of &&
            n.locale !== "ko" &&
            (Rl || Dt !== "onCompositionStart"
              ? Dt === "onCompositionEnd" && Rl && (bt = zf())
              : ((kn = N),
                (hr = "value" in kn ? kn.value : kn.textContent),
                (Rl = !0))),
          (nt = Tu(D, Dt)),
          0 < nt.length &&
            ((Dt = new Cf(Dt, t, null, n, N)),
            q.push({ event: Dt, listeners: nt }),
            bt
              ? (Dt.data = bt)
              : ((bt = wf(n)), bt !== null && (Dt.data = bt)))),
          (bt = bg ? vg(t, n) : Sg(t, n)) &&
            ((Dt = Tu(D, "onBeforeInput")),
            0 < Dt.length &&
              ((nt = new Cf("onBeforeInput", "beforeinput", null, n, N)),
              q.push({ event: nt, listeners: Dt }),
              (nt.data = bt))),
          sy(q, t, D, n, N));
      }
      gd(q, e);
    });
  }
  function ta(t, e, n) {
    return { instance: t, listener: e, currentTarget: n };
  }
  function Tu(t, e) {
    for (var n = e + "Capture", l = []; t !== null; ) {
      var a = t,
        o = a.stateNode;
      if (
        ((a = a.tag),
        (a !== 5 && a !== 26 && a !== 27) ||
          o === null ||
          ((a = xi(t, n)),
          a != null && l.unshift(ta(t, a, o)),
          (a = xi(t, e)),
          a != null && l.push(ta(t, a, o))),
        t.tag === 3)
      )
        return l;
      t = t.return;
    }
    return [];
  }
  function my(t) {
    if (t === null) return null;
    do t = t.return;
    while (t && t.tag !== 5 && t.tag !== 27);
    return t || null;
  }
  function bd(t, e, n, l, a) {
    for (var o = e._reactName, h = []; n !== null && n !== l; ) {
      var g = n,
        z = g.alternate,
        D = g.stateNode;
      if (((g = g.tag), z !== null && z === l)) break;
      ((g !== 5 && g !== 26 && g !== 27) ||
        D === null ||
        ((z = D),
        a
          ? ((D = xi(n, o)), D != null && h.unshift(ta(n, D, z)))
          : a || ((D = xi(n, o)), D != null && h.push(ta(n, D, z)))),
        (n = n.return));
    }
    h.length !== 0 && t.push({ event: e, listeners: h });
  }
  var gy = /\r\n?/g,
    yy = /\u0000|\uFFFD/g;
  function vd(t) {
    return (typeof t == "string" ? t : "" + t)
      .replace(
        gy,
        `
`,
      )
      .replace(yy, "");
  }
  function Sd(t, e) {
    return ((e = vd(e)), vd(t) === e);
  }
  function qt(t, e, n, l, a, o) {
    switch (n) {
      case "children":
        typeof l == "string"
          ? e === "body" || (e === "textarea" && l === "") || kl(t, l)
          : (typeof l == "number" || typeof l == "bigint") &&
            e !== "body" &&
            kl(t, "" + l);
        break;
      case "className":
        Oa(t, "class", l);
        break;
      case "tabIndex":
        Oa(t, "tabindex", l);
        break;
      case "dir":
      case "role":
      case "viewBox":
      case "width":
      case "height":
        Oa(t, n, l);
        break;
      case "style":
        Sf(t, l, o);
        break;
      case "data":
        if (e !== "object") {
          Oa(t, "data", l);
          break;
        }
      case "src":
      case "href":
        if (l === "" && (e !== "a" || n !== "href")) {
          t.removeAttribute(n);
          break;
        }
        if (
          l == null ||
          typeof l == "function" ||
          typeof l == "symbol" ||
          typeof l == "boolean"
        ) {
          t.removeAttribute(n);
          break;
        }
        ((l = Ma("" + l)), t.setAttribute(n, l));
        break;
      case "action":
      case "formAction":
        if (typeof l == "function") {
          t.setAttribute(
            n,
            "javascript:throw new Error('A React form was unexpectedly submitted. If you called form.submit() manually, consider using form.requestSubmit() instead. If you\\'re trying to use event.stopPropagation() in a submit event handler, consider also calling event.preventDefault().')",
          );
          break;
        } else
          typeof o == "function" &&
            (n === "formAction"
              ? (e !== "input" && qt(t, e, "name", a.name, a, null),
                qt(t, e, "formEncType", a.formEncType, a, null),
                qt(t, e, "formMethod", a.formMethod, a, null),
                qt(t, e, "formTarget", a.formTarget, a, null))
              : (qt(t, e, "encType", a.encType, a, null),
                qt(t, e, "method", a.method, a, null),
                qt(t, e, "target", a.target, a, null)));
        if (l == null || typeof l == "symbol" || typeof l == "boolean") {
          t.removeAttribute(n);
          break;
        }
        ((l = Ma("" + l)), t.setAttribute(n, l));
        break;
      case "onClick":
        l != null && (t.onclick = hn);
        break;
      case "onScroll":
        l != null && Ct("scroll", t);
        break;
      case "onScrollEnd":
        l != null && Ct("scrollend", t);
        break;
      case "dangerouslySetInnerHTML":
        if (l != null) {
          if (typeof l != "object" || !("__html" in l)) throw Error(c(61));
          if (((n = l.__html), n != null)) {
            if (a.children != null) throw Error(c(60));
            t.innerHTML = n;
          }
        }
        break;
      case "multiple":
        t.multiple = l && typeof l != "function" && typeof l != "symbol";
        break;
      case "muted":
        t.muted = l && typeof l != "function" && typeof l != "symbol";
        break;
      case "suppressContentEditableWarning":
      case "suppressHydrationWarning":
      case "defaultValue":
      case "defaultChecked":
      case "innerHTML":
      case "ref":
        break;
      case "autoFocus":
        break;
      case "xlinkHref":
        if (
          l == null ||
          typeof l == "function" ||
          typeof l == "boolean" ||
          typeof l == "symbol"
        ) {
          t.removeAttribute("xlink:href");
          break;
        }
        ((n = Ma("" + l)),
          t.setAttributeNS("http://www.w3.org/1999/xlink", "xlink:href", n));
        break;
      case "contentEditable":
      case "spellCheck":
      case "draggable":
      case "value":
      case "autoReverse":
      case "externalResourcesRequired":
      case "focusable":
      case "preserveAlpha":
        l != null && typeof l != "function" && typeof l != "symbol"
          ? t.setAttribute(n, "" + l)
          : t.removeAttribute(n);
        break;
      case "inert":
      case "allowFullScreen":
      case "async":
      case "autoPlay":
      case "controls":
      case "default":
      case "defer":
      case "disabled":
      case "disablePictureInPicture":
      case "disableRemotePlayback":
      case "formNoValidate":
      case "hidden":
      case "loop":
      case "noModule":
      case "noValidate":
      case "open":
      case "playsInline":
      case "readOnly":
      case "required":
      case "reversed":
      case "scoped":
      case "seamless":
      case "itemScope":
        l && typeof l != "function" && typeof l != "symbol"
          ? t.setAttribute(n, "")
          : t.removeAttribute(n);
        break;
      case "capture":
      case "download":
        l === !0
          ? t.setAttribute(n, "")
          : l !== !1 &&
              l != null &&
              typeof l != "function" &&
              typeof l != "symbol"
            ? t.setAttribute(n, l)
            : t.removeAttribute(n);
        break;
      case "cols":
      case "rows":
      case "size":
      case "span":
        l != null &&
        typeof l != "function" &&
        typeof l != "symbol" &&
        !isNaN(l) &&
        1 <= l
          ? t.setAttribute(n, l)
          : t.removeAttribute(n);
        break;
      case "rowSpan":
      case "start":
        l == null || typeof l == "function" || typeof l == "symbol" || isNaN(l)
          ? t.removeAttribute(n)
          : t.setAttribute(n, l);
        break;
      case "popover":
        (Ct("beforetoggle", t), Ct("toggle", t), _a(t, "popover", l));
        break;
      case "xlinkActuate":
        sn(t, "http://www.w3.org/1999/xlink", "xlink:actuate", l);
        break;
      case "xlinkArcrole":
        sn(t, "http://www.w3.org/1999/xlink", "xlink:arcrole", l);
        break;
      case "xlinkRole":
        sn(t, "http://www.w3.org/1999/xlink", "xlink:role", l);
        break;
      case "xlinkShow":
        sn(t, "http://www.w3.org/1999/xlink", "xlink:show", l);
        break;
      case "xlinkTitle":
        sn(t, "http://www.w3.org/1999/xlink", "xlink:title", l);
        break;
      case "xlinkType":
        sn(t, "http://www.w3.org/1999/xlink", "xlink:type", l);
        break;
      case "xmlBase":
        sn(t, "http://www.w3.org/XML/1998/namespace", "xml:base", l);
        break;
      case "xmlLang":
        sn(t, "http://www.w3.org/XML/1998/namespace", "xml:lang", l);
        break;
      case "xmlSpace":
        sn(t, "http://www.w3.org/XML/1998/namespace", "xml:space", l);
        break;
      case "is":
        _a(t, "is", l);
        break;
      case "innerText":
      case "textContent":
        break;
      default:
        (!(2 < n.length) ||
          (n[0] !== "o" && n[0] !== "O") ||
          (n[1] !== "n" && n[1] !== "N")) &&
          ((n = Vm.get(n) || n), _a(t, n, l));
    }
  }
  function Kc(t, e, n, l, a, o) {
    switch (n) {
      case "style":
        Sf(t, l, o);
        break;
      case "dangerouslySetInnerHTML":
        if (l != null) {
          if (typeof l != "object" || !("__html" in l)) throw Error(c(61));
          if (((n = l.__html), n != null)) {
            if (a.children != null) throw Error(c(60));
            t.innerHTML = n;
          }
        }
        break;
      case "children":
        typeof l == "string"
          ? kl(t, l)
          : (typeof l == "number" || typeof l == "bigint") && kl(t, "" + l);
        break;
      case "onScroll":
        l != null && Ct("scroll", t);
        break;
      case "onScrollEnd":
        l != null && Ct("scrollend", t);
        break;
      case "onClick":
        l != null && (t.onclick = hn);
        break;
      case "suppressContentEditableWarning":
      case "suppressHydrationWarning":
      case "innerHTML":
      case "ref":
        break;
      case "innerText":
      case "textContent":
        break;
      default:
        if (!sf.hasOwnProperty(n))
          t: {
            if (
              n[0] === "o" &&
              n[1] === "n" &&
              ((a = n.endsWith("Capture")),
              (e = n.slice(2, a ? n.length - 7 : void 0)),
              (o = t[Se] || null),
              (o = o != null ? o[n] : null),
              typeof o == "function" && t.removeEventListener(e, o, a),
              typeof l == "function")
            ) {
              (typeof o != "function" &&
                o !== null &&
                (n in t
                  ? (t[n] = null)
                  : t.hasAttribute(n) && t.removeAttribute(n)),
                t.addEventListener(e, l, a));
              break t;
            }
            n in t
              ? (t[n] = l)
              : l === !0
                ? t.setAttribute(n, "")
                : _a(t, n, l);
          }
    }
  }
  function he(t, e, n) {
    switch (e) {
      case "div":
      case "span":
      case "svg":
      case "path":
      case "a":
      case "g":
      case "p":
      case "li":
        break;
      case "img":
        (Ct("error", t), Ct("load", t));
        var l = !1,
          a = !1,
          o;
        for (o in n)
          if (n.hasOwnProperty(o)) {
            var h = n[o];
            if (h != null)
              switch (o) {
                case "src":
                  l = !0;
                  break;
                case "srcSet":
                  a = !0;
                  break;
                case "children":
                case "dangerouslySetInnerHTML":
                  throw Error(c(137, e));
                default:
                  qt(t, e, o, h, n, null);
              }
          }
        (a && qt(t, e, "srcSet", n.srcSet, n, null),
          l && qt(t, e, "src", n.src, n, null));
        return;
      case "input":
        Ct("invalid", t);
        var g = (o = h = a = null),
          z = null,
          D = null;
        for (l in n)
          if (n.hasOwnProperty(l)) {
            var N = n[l];
            if (N != null)
              switch (l) {
                case "name":
                  a = N;
                  break;
                case "type":
                  h = N;
                  break;
                case "checked":
                  z = N;
                  break;
                case "defaultChecked":
                  D = N;
                  break;
                case "value":
                  o = N;
                  break;
                case "defaultValue":
                  g = N;
                  break;
                case "children":
                case "dangerouslySetInnerHTML":
                  if (N != null) throw Error(c(137, e));
                  break;
                default:
                  qt(t, e, l, N, n, null);
              }
          }
        gf(t, o, g, z, D, h, a, !1);
        return;
      case "select":
        (Ct("invalid", t), (l = h = o = null));
        for (a in n)
          if (n.hasOwnProperty(a) && ((g = n[a]), g != null))
            switch (a) {
              case "value":
                o = g;
                break;
              case "defaultValue":
                h = g;
                break;
              case "multiple":
                l = g;
              default:
                qt(t, e, a, g, n, null);
            }
        ((e = o),
          (n = h),
          (t.multiple = !!l),
          e != null ? Ml(t, !!l, e, !1) : n != null && Ml(t, !!l, n, !0));
        return;
      case "textarea":
        (Ct("invalid", t), (o = a = l = null));
        for (h in n)
          if (n.hasOwnProperty(h) && ((g = n[h]), g != null))
            switch (h) {
              case "value":
                l = g;
                break;
              case "defaultValue":
                a = g;
                break;
              case "children":
                o = g;
                break;
              case "dangerouslySetInnerHTML":
                if (g != null) throw Error(c(91));
                break;
              default:
                qt(t, e, h, g, n, null);
            }
        bf(t, l, a, o);
        return;
      case "option":
        for (z in n)
          n.hasOwnProperty(z) &&
            ((l = n[z]), l != null) &&
            (z === "selected"
              ? (t.selected =
                  l && typeof l != "function" && typeof l != "symbol")
              : qt(t, e, z, l, n, null));
        return;
      case "dialog":
        (Ct("beforetoggle", t),
          Ct("toggle", t),
          Ct("cancel", t),
          Ct("close", t));
        break;
      case "iframe":
      case "object":
        Ct("load", t);
        break;
      case "video":
      case "audio":
        for (l = 0; l < Pi.length; l++) Ct(Pi[l], t);
        break;
      case "image":
        (Ct("error", t), Ct("load", t));
        break;
      case "details":
        Ct("toggle", t);
        break;
      case "embed":
      case "source":
      case "link":
        (Ct("error", t), Ct("load", t));
      case "area":
      case "base":
      case "br":
      case "col":
      case "hr":
      case "keygen":
      case "meta":
      case "param":
      case "track":
      case "wbr":
      case "menuitem":
        for (D in n)
          if (n.hasOwnProperty(D) && ((l = n[D]), l != null))
            switch (D) {
              case "children":
              case "dangerouslySetInnerHTML":
                throw Error(c(137, e));
              default:
                qt(t, e, D, l, n, null);
            }
        return;
      default:
        if (rr(e)) {
          for (N in n)
            n.hasOwnProperty(N) &&
              ((l = n[N]), l !== void 0 && Kc(t, e, N, l, n, void 0));
          return;
        }
    }
    for (g in n)
      n.hasOwnProperty(g) && ((l = n[g]), l != null && qt(t, e, g, l, n, null));
  }
  function by(t, e, n, l) {
    switch (e) {
      case "div":
      case "span":
      case "svg":
      case "path":
      case "a":
      case "g":
      case "p":
      case "li":
        break;
      case "input":
        var a = null,
          o = null,
          h = null,
          g = null,
          z = null,
          D = null,
          N = null;
        for (w in n) {
          var q = n[w];
          if (n.hasOwnProperty(w) && q != null)
            switch (w) {
              case "checked":
                break;
              case "value":
                break;
              case "defaultValue":
                z = q;
              default:
                l.hasOwnProperty(w) || qt(t, e, w, null, l, q);
            }
        }
        for (var k in l) {
          var w = l[k];
          if (((q = n[k]), l.hasOwnProperty(k) && (w != null || q != null)))
            switch (k) {
              case "type":
                o = w;
                break;
              case "name":
                a = w;
                break;
              case "checked":
                D = w;
                break;
              case "defaultChecked":
                N = w;
                break;
              case "value":
                h = w;
                break;
              case "defaultValue":
                g = w;
                break;
              case "children":
              case "dangerouslySetInnerHTML":
                if (w != null) throw Error(c(137, e));
                break;
              default:
                w !== q && qt(t, e, k, w, l, q);
            }
        }
        ar(t, h, g, z, D, N, o, a);
        return;
      case "select":
        w = h = g = k = null;
        for (o in n)
          if (((z = n[o]), n.hasOwnProperty(o) && z != null))
            switch (o) {
              case "value":
                break;
              case "multiple":
                w = z;
              default:
                l.hasOwnProperty(o) || qt(t, e, o, null, l, z);
            }
        for (a in l)
          if (
            ((o = l[a]),
            (z = n[a]),
            l.hasOwnProperty(a) && (o != null || z != null))
          )
            switch (a) {
              case "value":
                k = o;
                break;
              case "defaultValue":
                g = o;
                break;
              case "multiple":
                h = o;
              default:
                o !== z && qt(t, e, a, o, l, z);
            }
        ((e = g),
          (n = h),
          (l = w),
          k != null
            ? Ml(t, !!n, k, !1)
            : !!l != !!n &&
              (e != null ? Ml(t, !!n, e, !0) : Ml(t, !!n, n ? [] : "", !1)));
        return;
      case "textarea":
        w = k = null;
        for (g in n)
          if (
            ((a = n[g]),
            n.hasOwnProperty(g) && a != null && !l.hasOwnProperty(g))
          )
            switch (g) {
              case "value":
                break;
              case "children":
                break;
              default:
                qt(t, e, g, null, l, a);
            }
        for (h in l)
          if (
            ((a = l[h]),
            (o = n[h]),
            l.hasOwnProperty(h) && (a != null || o != null))
          )
            switch (h) {
              case "value":
                k = a;
                break;
              case "defaultValue":
                w = a;
                break;
              case "children":
                break;
              case "dangerouslySetInnerHTML":
                if (a != null) throw Error(c(91));
                break;
              default:
                a !== o && qt(t, e, h, a, l, o);
            }
        yf(t, k, w);
        return;
      case "option":
        for (var et in n)
          ((k = n[et]),
            n.hasOwnProperty(et) &&
              k != null &&
              !l.hasOwnProperty(et) &&
              (et === "selected"
                ? (t.selected = !1)
                : qt(t, e, et, null, l, k)));
        for (z in l)
          ((k = l[z]),
            (w = n[z]),
            l.hasOwnProperty(z) &&
              k !== w &&
              (k != null || w != null) &&
              (z === "selected"
                ? (t.selected =
                    k && typeof k != "function" && typeof k != "symbol")
                : qt(t, e, z, k, l, w)));
        return;
      case "img":
      case "link":
      case "area":
      case "base":
      case "br":
      case "col":
      case "embed":
      case "hr":
      case "keygen":
      case "meta":
      case "param":
      case "source":
      case "track":
      case "wbr":
      case "menuitem":
        for (var ot in n)
          ((k = n[ot]),
            n.hasOwnProperty(ot) &&
              k != null &&
              !l.hasOwnProperty(ot) &&
              qt(t, e, ot, null, l, k));
        for (D in l)
          if (
            ((k = l[D]),
            (w = n[D]),
            l.hasOwnProperty(D) && k !== w && (k != null || w != null))
          )
            switch (D) {
              case "children":
              case "dangerouslySetInnerHTML":
                if (k != null) throw Error(c(137, e));
                break;
              default:
                qt(t, e, D, k, l, w);
            }
        return;
      default:
        if (rr(e)) {
          for (var Yt in n)
            ((k = n[Yt]),
              n.hasOwnProperty(Yt) &&
                k !== void 0 &&
                !l.hasOwnProperty(Yt) &&
                Kc(t, e, Yt, void 0, l, k));
          for (N in l)
            ((k = l[N]),
              (w = n[N]),
              !l.hasOwnProperty(N) ||
                k === w ||
                (k === void 0 && w === void 0) ||
                Kc(t, e, N, k, l, w));
          return;
        }
    }
    for (var _ in n)
      ((k = n[_]),
        n.hasOwnProperty(_) &&
          k != null &&
          !l.hasOwnProperty(_) &&
          qt(t, e, _, null, l, k));
    for (q in l)
      ((k = l[q]),
        (w = n[q]),
        !l.hasOwnProperty(q) ||
          k === w ||
          (k == null && w == null) ||
          qt(t, e, q, k, l, w));
  }
  function xd(t) {
    switch (t) {
      case "css":
      case "script":
      case "font":
      case "img":
      case "image":
      case "input":
      case "link":
        return !0;
      default:
        return !1;
    }
  }
  function vy() {
    if (typeof performance.getEntriesByType == "function") {
      for (
        var t = 0, e = 0, n = performance.getEntriesByType("resource"), l = 0;
        l < n.length;
        l++
      ) {
        var a = n[l],
          o = a.transferSize,
          h = a.initiatorType,
          g = a.duration;
        if (o && g && xd(h)) {
          for (h = 0, g = a.responseEnd, l += 1; l < n.length; l++) {
            var z = n[l],
              D = z.startTime;
            if (D > g) break;
            var N = z.transferSize,
              q = z.initiatorType;
            N &&
              xd(q) &&
              ((z = z.responseEnd), (h += N * (z < g ? 1 : (g - D) / (z - D))));
          }
          if ((--l, (e += (8 * (o + h)) / (a.duration / 1e3)), t++, 10 < t))
            break;
        }
      }
      if (0 < t) return e / t / 1e6;
    }
    return navigator.connection &&
      ((t = navigator.connection.downlink), typeof t == "number")
      ? t
      : 5;
  }
  var Jc = null,
    Fc = null;
  function Au(t) {
    return t.nodeType === 9 ? t : t.ownerDocument;
  }
  function Ed(t) {
    switch (t) {
      case "http://www.w3.org/2000/svg":
        return 1;
      case "http://www.w3.org/1998/Math/MathML":
        return 2;
      default:
        return 0;
    }
  }
  function zd(t, e) {
    if (t === 0)
      switch (e) {
        case "svg":
          return 1;
        case "math":
          return 2;
        default:
          return 0;
      }
    return t === 1 && e === "foreignObject" ? 0 : t;
  }
  function Ic(t, e) {
    return (
      t === "textarea" ||
      t === "noscript" ||
      typeof e.children == "string" ||
      typeof e.children == "number" ||
      typeof e.children == "bigint" ||
      (typeof e.dangerouslySetInnerHTML == "object" &&
        e.dangerouslySetInnerHTML !== null &&
        e.dangerouslySetInnerHTML.__html != null)
    );
  }
  var Wc = null;
  function Sy() {
    var t = window.event;
    return t && t.type === "popstate"
      ? t === Wc
        ? !1
        : ((Wc = t), !0)
      : ((Wc = null), !1);
  }
  var Td = typeof setTimeout == "function" ? setTimeout : void 0,
    xy = typeof clearTimeout == "function" ? clearTimeout : void 0,
    Ad = typeof Promise == "function" ? Promise : void 0,
    Ey =
      typeof queueMicrotask == "function"
        ? queueMicrotask
        : typeof Ad < "u"
          ? function (t) {
              return Ad.resolve(null).then(t).catch(zy);
            }
          : Td;
  function zy(t) {
    setTimeout(function () {
      throw t;
    });
  }
  function Jn(t) {
    return t === "head";
  }
  function Cd(t, e) {
    var n = e,
      l = 0;
    do {
      var a = n.nextSibling;
      if ((t.removeChild(n), a && a.nodeType === 8))
        if (((n = a.data), n === "/$" || n === "/&")) {
          if (l === 0) {
            (t.removeChild(a), ci(e));
            return;
          }
          l--;
        } else if (
          n === "$" ||
          n === "$?" ||
          n === "$~" ||
          n === "$!" ||
          n === "&"
        )
          l++;
        else if (n === "html") ea(t.ownerDocument.documentElement);
        else if (n === "head") {
          ((n = t.ownerDocument.head), ea(n));
          for (var o = n.firstChild; o; ) {
            var h = o.nextSibling,
              g = o.nodeName;
            (o[vi] ||
              g === "SCRIPT" ||
              g === "STYLE" ||
              (g === "LINK" && o.rel.toLowerCase() === "stylesheet") ||
              n.removeChild(o),
              (o = h));
          }
        } else n === "body" && ea(t.ownerDocument.body);
      n = a;
    } while (n);
    ci(e);
  }
  function _d(t, e) {
    var n = t;
    t = 0;
    do {
      var l = n.nextSibling;
      if (
        (n.nodeType === 1
          ? e
            ? ((n._stashedDisplay = n.style.display),
              (n.style.display = "none"))
            : ((n.style.display = n._stashedDisplay || ""),
              n.getAttribute("style") === "" && n.removeAttribute("style"))
          : n.nodeType === 3 &&
            (e
              ? ((n._stashedText = n.nodeValue), (n.nodeValue = ""))
              : (n.nodeValue = n._stashedText || "")),
        l && l.nodeType === 8)
      )
        if (((n = l.data), n === "/$")) {
          if (t === 0) break;
          t--;
        } else (n !== "$" && n !== "$?" && n !== "$~" && n !== "$!") || t++;
      n = l;
    } while (n);
  }
  function $c(t) {
    var e = t.firstChild;
    for (e && e.nodeType === 10 && (e = e.nextSibling); e; ) {
      var n = e;
      switch (((e = e.nextSibling), n.nodeName)) {
        case "HTML":
        case "HEAD":
        case "BODY":
          ($c(n), lr(n));
          continue;
        case "SCRIPT":
        case "STYLE":
          continue;
        case "LINK":
          if (n.rel.toLowerCase() === "stylesheet") continue;
      }
      t.removeChild(n);
    }
  }
  function Ty(t, e, n, l) {
    for (; t.nodeType === 1; ) {
      var a = n;
      if (t.nodeName.toLowerCase() !== e.toLowerCase()) {
        if (!l && (t.nodeName !== "INPUT" || t.type !== "hidden")) break;
      } else if (l) {
        if (!t[vi])
          switch (e) {
            case "meta":
              if (!t.hasAttribute("itemprop")) break;
              return t;
            case "link":
              if (
                ((o = t.getAttribute("rel")),
                o === "stylesheet" && t.hasAttribute("data-precedence"))
              )
                break;
              if (
                o !== a.rel ||
                t.getAttribute("href") !==
                  (a.href == null || a.href === "" ? null : a.href) ||
                t.getAttribute("crossorigin") !==
                  (a.crossOrigin == null ? null : a.crossOrigin) ||
                t.getAttribute("title") !== (a.title == null ? null : a.title)
              )
                break;
              return t;
            case "style":
              if (t.hasAttribute("data-precedence")) break;
              return t;
            case "script":
              if (
                ((o = t.getAttribute("src")),
                (o !== (a.src == null ? null : a.src) ||
                  t.getAttribute("type") !== (a.type == null ? null : a.type) ||
                  t.getAttribute("crossorigin") !==
                    (a.crossOrigin == null ? null : a.crossOrigin)) &&
                  o &&
                  t.hasAttribute("async") &&
                  !t.hasAttribute("itemprop"))
              )
                break;
              return t;
            default:
              return t;
          }
      } else if (e === "input" && t.type === "hidden") {
        var o = a.name == null ? null : "" + a.name;
        if (a.type === "hidden" && t.getAttribute("name") === o) return t;
      } else return t;
      if (((t = Je(t.nextSibling)), t === null)) break;
    }
    return null;
  }
  function Ay(t, e, n) {
    if (e === "") return null;
    for (; t.nodeType !== 3; )
      if (
        ((t.nodeType !== 1 || t.nodeName !== "INPUT" || t.type !== "hidden") &&
          !n) ||
        ((t = Je(t.nextSibling)), t === null)
      )
        return null;
    return t;
  }
  function Od(t, e) {
    for (; t.nodeType !== 8; )
      if (
        ((t.nodeType !== 1 || t.nodeName !== "INPUT" || t.type !== "hidden") &&
          !e) ||
        ((t = Je(t.nextSibling)), t === null)
      )
        return null;
    return t;
  }
  function Pc(t) {
    return t.data === "$?" || t.data === "$~";
  }
  function to(t) {
    return (
      t.data === "$!" ||
      (t.data === "$?" && t.ownerDocument.readyState !== "loading")
    );
  }
  function Cy(t, e) {
    var n = t.ownerDocument;
    if (t.data === "$~") t._reactRetry = e;
    else if (t.data !== "$?" || n.readyState !== "loading") e();
    else {
      var l = function () {
        (e(), n.removeEventListener("DOMContentLoaded", l));
      };
      (n.addEventListener("DOMContentLoaded", l), (t._reactRetry = l));
    }
  }
  function Je(t) {
    for (; t != null; t = t.nextSibling) {
      var e = t.nodeType;
      if (e === 1 || e === 3) break;
      if (e === 8) {
        if (
          ((e = t.data),
          e === "$" ||
            e === "$!" ||
            e === "$?" ||
            e === "$~" ||
            e === "&" ||
            e === "F!" ||
            e === "F")
        )
          break;
        if (e === "/$" || e === "/&") return null;
      }
    }
    return t;
  }
  var eo = null;
  function Dd(t) {
    t = t.nextSibling;
    for (var e = 0; t; ) {
      if (t.nodeType === 8) {
        var n = t.data;
        if (n === "/$" || n === "/&") {
          if (e === 0) return Je(t.nextSibling);
          e--;
        } else
          (n !== "$" && n !== "$!" && n !== "$?" && n !== "$~" && n !== "&") ||
            e++;
      }
      t = t.nextSibling;
    }
    return null;
  }
  function Md(t) {
    t = t.previousSibling;
    for (var e = 0; t; ) {
      if (t.nodeType === 8) {
        var n = t.data;
        if (n === "$" || n === "$!" || n === "$?" || n === "$~" || n === "&") {
          if (e === 0) return t;
          e--;
        } else (n !== "/$" && n !== "/&") || e++;
      }
      t = t.previousSibling;
    }
    return null;
  }
  function kd(t, e, n) {
    switch (((e = Au(n)), t)) {
      case "html":
        if (((t = e.documentElement), !t)) throw Error(c(452));
        return t;
      case "head":
        if (((t = e.head), !t)) throw Error(c(453));
        return t;
      case "body":
        if (((t = e.body), !t)) throw Error(c(454));
        return t;
      default:
        throw Error(c(451));
    }
  }
  function ea(t) {
    for (var e = t.attributes; e.length; ) t.removeAttributeNode(e[0]);
    lr(t);
  }
  var Fe = new Map(),
    wd = new Set();
  function Cu(t) {
    return typeof t.getRootNode == "function"
      ? t.getRootNode()
      : t.nodeType === 9
        ? t
        : t.ownerDocument;
  }
  var On = B.d;
  B.d = { f: _y, r: Oy, D: Dy, C: My, L: ky, m: wy, X: Ry, S: Ny, M: Uy };
  function _y() {
    var t = On.f(),
      e = yu();
    return t || e;
  }
  function Oy(t) {
    var e = _l(t);
    e !== null && e.tag === 5 && e.type === "form" ? Fs(e) : On.r(t);
  }
  var ai = typeof document > "u" ? null : document;
  function Nd(t, e, n) {
    var l = ai;
    if (l && typeof e == "string" && e) {
      var a = Ye(e);
      ((a = 'link[rel="' + t + '"][href="' + a + '"]'),
        typeof n == "string" && (a += '[crossorigin="' + n + '"]'),
        wd.has(a) ||
          (wd.add(a),
          (t = { rel: t, crossOrigin: n, href: e }),
          l.querySelector(a) === null &&
            ((e = l.createElement("link")),
            he(e, "link", t),
            ue(e),
            l.head.appendChild(e))));
    }
  }
  function Dy(t) {
    (On.D(t), Nd("dns-prefetch", t, null));
  }
  function My(t, e) {
    (On.C(t, e), Nd("preconnect", t, e));
  }
  function ky(t, e, n) {
    On.L(t, e, n);
    var l = ai;
    if (l && t && e) {
      var a = 'link[rel="preload"][as="' + Ye(e) + '"]';
      e === "image" && n && n.imageSrcSet
        ? ((a += '[imagesrcset="' + Ye(n.imageSrcSet) + '"]'),
          typeof n.imageSizes == "string" &&
            (a += '[imagesizes="' + Ye(n.imageSizes) + '"]'))
        : (a += '[href="' + Ye(t) + '"]');
      var o = a;
      switch (e) {
        case "style":
          o = ui(t);
          break;
        case "script":
          o = ri(t);
      }
      Fe.has(o) ||
        ((t = v(
          {
            rel: "preload",
            href: e === "image" && n && n.imageSrcSet ? void 0 : t,
            as: e,
          },
          n,
        )),
        Fe.set(o, t),
        l.querySelector(a) !== null ||
          (e === "style" && l.querySelector(na(o))) ||
          (e === "script" && l.querySelector(la(o))) ||
          ((e = l.createElement("link")),
          he(e, "link", t),
          ue(e),
          l.head.appendChild(e)));
    }
  }
  function wy(t, e) {
    On.m(t, e);
    var n = ai;
    if (n && t) {
      var l = e && typeof e.as == "string" ? e.as : "script",
        a =
          'link[rel="modulepreload"][as="' + Ye(l) + '"][href="' + Ye(t) + '"]',
        o = a;
      switch (l) {
        case "audioworklet":
        case "paintworklet":
        case "serviceworker":
        case "sharedworker":
        case "worker":
        case "script":
          o = ri(t);
      }
      if (
        !Fe.has(o) &&
        ((t = v({ rel: "modulepreload", href: t }, e)),
        Fe.set(o, t),
        n.querySelector(a) === null)
      ) {
        switch (l) {
          case "audioworklet":
          case "paintworklet":
          case "serviceworker":
          case "sharedworker":
          case "worker":
          case "script":
            if (n.querySelector(la(o))) return;
        }
        ((l = n.createElement("link")),
          he(l, "link", t),
          ue(l),
          n.head.appendChild(l));
      }
    }
  }
  function Ny(t, e, n) {
    On.S(t, e, n);
    var l = ai;
    if (l && t) {
      var a = Ol(l).hoistableStyles,
        o = ui(t);
      e = e || "default";
      var h = a.get(o);
      if (!h) {
        var g = { loading: 0, preload: null };
        if ((h = l.querySelector(na(o)))) g.loading = 5;
        else {
          ((t = v({ rel: "stylesheet", href: t, "data-precedence": e }, n)),
            (n = Fe.get(o)) && no(t, n));
          var z = (h = l.createElement("link"));
          (ue(z),
            he(z, "link", t),
            (z._p = new Promise(function (D, N) {
              ((z.onload = D), (z.onerror = N));
            })),
            z.addEventListener("load", function () {
              g.loading |= 1;
            }),
            z.addEventListener("error", function () {
              g.loading |= 2;
            }),
            (g.loading |= 4),
            _u(h, e, l));
        }
        ((h = { type: "stylesheet", instance: h, count: 1, state: g }),
          a.set(o, h));
      }
    }
  }
  function Ry(t, e) {
    On.X(t, e);
    var n = ai;
    if (n && t) {
      var l = Ol(n).hoistableScripts,
        a = ri(t),
        o = l.get(a);
      o ||
        ((o = n.querySelector(la(a))),
        o ||
          ((t = v({ src: t, async: !0 }, e)),
          (e = Fe.get(a)) && lo(t, e),
          (o = n.createElement("script")),
          ue(o),
          he(o, "link", t),
          n.head.appendChild(o)),
        (o = { type: "script", instance: o, count: 1, state: null }),
        l.set(a, o));
    }
  }
  function Uy(t, e) {
    On.M(t, e);
    var n = ai;
    if (n && t) {
      var l = Ol(n).hoistableScripts,
        a = ri(t),
        o = l.get(a);
      o ||
        ((o = n.querySelector(la(a))),
        o ||
          ((t = v({ src: t, async: !0, type: "module" }, e)),
          (e = Fe.get(a)) && lo(t, e),
          (o = n.createElement("script")),
          ue(o),
          he(o, "link", t),
          n.head.appendChild(o)),
        (o = { type: "script", instance: o, count: 1, state: null }),
        l.set(a, o));
    }
  }
  function Rd(t, e, n, l) {
    var a = (a = at.current) ? Cu(a) : null;
    if (!a) throw Error(c(446));
    switch (t) {
      case "meta":
      case "title":
        return null;
      case "style":
        return typeof n.precedence == "string" && typeof n.href == "string"
          ? ((e = ui(n.href)),
            (n = Ol(a).hoistableStyles),
            (l = n.get(e)),
            l ||
              ((l = { type: "style", instance: null, count: 0, state: null }),
              n.set(e, l)),
            l)
          : { type: "void", instance: null, count: 0, state: null };
      case "link":
        if (
          n.rel === "stylesheet" &&
          typeof n.href == "string" &&
          typeof n.precedence == "string"
        ) {
          t = ui(n.href);
          var o = Ol(a).hoistableStyles,
            h = o.get(t);
          if (
            (h ||
              ((a = a.ownerDocument || a),
              (h = {
                type: "stylesheet",
                instance: null,
                count: 0,
                state: { loading: 0, preload: null },
              }),
              o.set(t, h),
              (o = a.querySelector(na(t))) &&
                !o._p &&
                ((h.instance = o), (h.state.loading = 5)),
              Fe.has(t) ||
                ((n = {
                  rel: "preload",
                  as: "style",
                  href: n.href,
                  crossOrigin: n.crossOrigin,
                  integrity: n.integrity,
                  media: n.media,
                  hrefLang: n.hrefLang,
                  referrerPolicy: n.referrerPolicy,
                }),
                Fe.set(t, n),
                o || By(a, t, n, h.state))),
            e && l === null)
          )
            throw Error(c(528, ""));
          return h;
        }
        if (e && l !== null) throw Error(c(529, ""));
        return null;
      case "script":
        return (
          (e = n.async),
          (n = n.src),
          typeof n == "string" &&
          e &&
          typeof e != "function" &&
          typeof e != "symbol"
            ? ((e = ri(n)),
              (n = Ol(a).hoistableScripts),
              (l = n.get(e)),
              l ||
                ((l = {
                  type: "script",
                  instance: null,
                  count: 0,
                  state: null,
                }),
                n.set(e, l)),
              l)
            : { type: "void", instance: null, count: 0, state: null }
        );
      default:
        throw Error(c(444, t));
    }
  }
  function ui(t) {
    return 'href="' + Ye(t) + '"';
  }
  function na(t) {
    return 'link[rel="stylesheet"][' + t + "]";
  }
  function Ud(t) {
    return v({}, t, { "data-precedence": t.precedence, precedence: null });
  }
  function By(t, e, n, l) {
    t.querySelector('link[rel="preload"][as="style"][' + e + "]")
      ? (l.loading = 1)
      : ((e = t.createElement("link")),
        (l.preload = e),
        e.addEventListener("load", function () {
          return (l.loading |= 1);
        }),
        e.addEventListener("error", function () {
          return (l.loading |= 2);
        }),
        he(e, "link", n),
        ue(e),
        t.head.appendChild(e));
  }
  function ri(t) {
    return '[src="' + Ye(t) + '"]';
  }
  function la(t) {
    return "script[async]" + t;
  }
  function Bd(t, e, n) {
    if ((e.count++, e.instance === null))
      switch (e.type) {
        case "style":
          var l = t.querySelector('style[data-href~="' + Ye(n.href) + '"]');
          if (l) return ((e.instance = l), ue(l), l);
          var a = v({}, n, {
            "data-href": n.href,
            "data-precedence": n.precedence,
            href: null,
            precedence: null,
          });
          return (
            (l = (t.ownerDocument || t).createElement("style")),
            ue(l),
            he(l, "style", a),
            _u(l, n.precedence, t),
            (e.instance = l)
          );
        case "stylesheet":
          a = ui(n.href);
          var o = t.querySelector(na(a));
          if (o) return ((e.state.loading |= 4), (e.instance = o), ue(o), o);
          ((l = Ud(n)),
            (a = Fe.get(a)) && no(l, a),
            (o = (t.ownerDocument || t).createElement("link")),
            ue(o));
          var h = o;
          return (
            (h._p = new Promise(function (g, z) {
              ((h.onload = g), (h.onerror = z));
            })),
            he(o, "link", l),
            (e.state.loading |= 4),
            _u(o, n.precedence, t),
            (e.instance = o)
          );
        case "script":
          return (
            (o = ri(n.src)),
            (a = t.querySelector(la(o)))
              ? ((e.instance = a), ue(a), a)
              : ((l = n),
                (a = Fe.get(o)) && ((l = v({}, n)), lo(l, a)),
                (t = t.ownerDocument || t),
                (a = t.createElement("script")),
                ue(a),
                he(a, "link", l),
                t.head.appendChild(a),
                (e.instance = a))
          );
        case "void":
          return null;
        default:
          throw Error(c(443, e.type));
      }
    else
      e.type === "stylesheet" &&
        (e.state.loading & 4) === 0 &&
        ((l = e.instance), (e.state.loading |= 4), _u(l, n.precedence, t));
    return e.instance;
  }
  function _u(t, e, n) {
    for (
      var l = n.querySelectorAll(
          'link[rel="stylesheet"][data-precedence],style[data-precedence]',
        ),
        a = l.length ? l[l.length - 1] : null,
        o = a,
        h = 0;
      h < l.length;
      h++
    ) {
      var g = l[h];
      if (g.dataset.precedence === e) o = g;
      else if (o !== a) break;
    }
    o
      ? o.parentNode.insertBefore(t, o.nextSibling)
      : ((e = n.nodeType === 9 ? n.head : n), e.insertBefore(t, e.firstChild));
  }
  function no(t, e) {
    (t.crossOrigin == null && (t.crossOrigin = e.crossOrigin),
      t.referrerPolicy == null && (t.referrerPolicy = e.referrerPolicy),
      t.title == null && (t.title = e.title));
  }
  function lo(t, e) {
    (t.crossOrigin == null && (t.crossOrigin = e.crossOrigin),
      t.referrerPolicy == null && (t.referrerPolicy = e.referrerPolicy),
      t.integrity == null && (t.integrity = e.integrity));
  }
  var Ou = null;
  function jd(t, e, n) {
    if (Ou === null) {
      var l = new Map(),
        a = (Ou = new Map());
      a.set(n, l);
    } else ((a = Ou), (l = a.get(n)), l || ((l = new Map()), a.set(n, l)));
    if (l.has(t)) return l;
    for (
      l.set(t, null), n = n.getElementsByTagName(t), a = 0;
      a < n.length;
      a++
    ) {
      var o = n[a];
      if (
        !(
          o[vi] ||
          o[ce] ||
          (t === "link" && o.getAttribute("rel") === "stylesheet")
        ) &&
        o.namespaceURI !== "http://www.w3.org/2000/svg"
      ) {
        var h = o.getAttribute(e) || "";
        h = t + h;
        var g = l.get(h);
        g ? g.push(o) : l.set(h, [o]);
      }
    }
    return l;
  }
  function Hd(t, e, n) {
    ((t = t.ownerDocument || t),
      t.head.insertBefore(
        n,
        e === "title" ? t.querySelector("head > title") : null,
      ));
  }
  function jy(t, e, n) {
    if (n === 1 || e.itemProp != null) return !1;
    switch (t) {
      case "meta":
      case "title":
        return !0;
      case "style":
        if (
          typeof e.precedence != "string" ||
          typeof e.href != "string" ||
          e.href === ""
        )
          break;
        return !0;
      case "link":
        if (
          typeof e.rel != "string" ||
          typeof e.href != "string" ||
          e.href === "" ||
          e.onLoad ||
          e.onError
        )
          break;
        return e.rel === "stylesheet"
          ? ((t = e.disabled), typeof e.precedence == "string" && t == null)
          : !0;
      case "script":
        if (
          e.async &&
          typeof e.async != "function" &&
          typeof e.async != "symbol" &&
          !e.onLoad &&
          !e.onError &&
          e.src &&
          typeof e.src == "string"
        )
          return !0;
    }
    return !1;
  }
  function Ld(t) {
    return !(t.type === "stylesheet" && (t.state.loading & 3) === 0);
  }
  function Hy(t, e, n, l) {
    if (
      n.type === "stylesheet" &&
      (typeof l.media != "string" || matchMedia(l.media).matches !== !1) &&
      (n.state.loading & 4) === 0
    ) {
      if (n.instance === null) {
        var a = ui(l.href),
          o = e.querySelector(na(a));
        if (o) {
          ((e = o._p),
            e !== null &&
              typeof e == "object" &&
              typeof e.then == "function" &&
              (t.count++, (t = Du.bind(t)), e.then(t, t)),
            (n.state.loading |= 4),
            (n.instance = o),
            ue(o));
          return;
        }
        ((o = e.ownerDocument || e),
          (l = Ud(l)),
          (a = Fe.get(a)) && no(l, a),
          (o = o.createElement("link")),
          ue(o));
        var h = o;
        ((h._p = new Promise(function (g, z) {
          ((h.onload = g), (h.onerror = z));
        })),
          he(o, "link", l),
          (n.instance = o));
      }
      (t.stylesheets === null && (t.stylesheets = new Map()),
        t.stylesheets.set(n, e),
        (e = n.state.preload) &&
          (n.state.loading & 3) === 0 &&
          (t.count++,
          (n = Du.bind(t)),
          e.addEventListener("load", n),
          e.addEventListener("error", n)));
    }
  }
  var io = 0;
  function Ly(t, e) {
    return (
      t.stylesheets && t.count === 0 && ku(t, t.stylesheets),
      0 < t.count || 0 < t.imgCount
        ? function (n) {
            var l = setTimeout(function () {
              if ((t.stylesheets && ku(t, t.stylesheets), t.unsuspend)) {
                var o = t.unsuspend;
                ((t.unsuspend = null), o());
              }
            }, 6e4 + e);
            0 < t.imgBytes && io === 0 && (io = 62500 * vy());
            var a = setTimeout(
              function () {
                if (
                  ((t.waitingForImages = !1),
                  t.count === 0 &&
                    (t.stylesheets && ku(t, t.stylesheets), t.unsuspend))
                ) {
                  var o = t.unsuspend;
                  ((t.unsuspend = null), o());
                }
              },
              (t.imgBytes > io ? 50 : 800) + e,
            );
            return (
              (t.unsuspend = n),
              function () {
                ((t.unsuspend = null), clearTimeout(l), clearTimeout(a));
              }
            );
          }
        : null
    );
  }
  function Du() {
    if (
      (this.count--,
      this.count === 0 && (this.imgCount === 0 || !this.waitingForImages))
    ) {
      if (this.stylesheets) ku(this, this.stylesheets);
      else if (this.unsuspend) {
        var t = this.unsuspend;
        ((this.unsuspend = null), t());
      }
    }
  }
  var Mu = null;
  function ku(t, e) {
    ((t.stylesheets = null),
      t.unsuspend !== null &&
        (t.count++,
        (Mu = new Map()),
        e.forEach(qy, t),
        (Mu = null),
        Du.call(t)));
  }
  function qy(t, e) {
    if (!(e.state.loading & 4)) {
      var n = Mu.get(t);
      if (n) var l = n.get(null);
      else {
        ((n = new Map()), Mu.set(t, n));
        for (
          var a = t.querySelectorAll(
              "link[data-precedence],style[data-precedence]",
            ),
            o = 0;
          o < a.length;
          o++
        ) {
          var h = a[o];
          (h.nodeName === "LINK" || h.getAttribute("media") !== "not all") &&
            (n.set(h.dataset.precedence, h), (l = h));
        }
        l && n.set(null, l);
      }
      ((a = e.instance),
        (h = a.getAttribute("data-precedence")),
        (o = n.get(h) || l),
        o === l && n.set(null, a),
        n.set(h, a),
        this.count++,
        (l = Du.bind(this)),
        a.addEventListener("load", l),
        a.addEventListener("error", l),
        o
          ? o.parentNode.insertBefore(a, o.nextSibling)
          : ((t = t.nodeType === 9 ? t.head : t),
            t.insertBefore(a, t.firstChild)),
        (e.state.loading |= 4));
    }
  }
  var ia = {
    $$typeof: K,
    Provider: null,
    Consumer: null,
    _currentValue: P,
    _currentValue2: P,
    _threadCount: 0,
  };
  function Yy(t, e, n, l, a, o, h, g, z) {
    ((this.tag = 1),
      (this.containerInfo = t),
      (this.pingCache = this.current = this.pendingChildren = null),
      (this.timeoutHandle = -1),
      (this.callbackNode =
        this.next =
        this.pendingContext =
        this.context =
        this.cancelPendingCommit =
          null),
      (this.callbackPriority = 0),
      (this.expirationTimes = Pu(-1)),
      (this.entangledLanes =
        this.shellSuspendCounter =
        this.errorRecoveryDisabledLanes =
        this.expiredLanes =
        this.warmLanes =
        this.pingedLanes =
        this.suspendedLanes =
        this.pendingLanes =
          0),
      (this.entanglements = Pu(0)),
      (this.hiddenUpdates = Pu(null)),
      (this.identifierPrefix = l),
      (this.onUncaughtError = a),
      (this.onCaughtError = o),
      (this.onRecoverableError = h),
      (this.pooledCache = null),
      (this.pooledCacheLanes = 0),
      (this.formState = z),
      (this.incompleteTransitions = new Map()));
  }
  function qd(t, e, n, l, a, o, h, g, z, D, N, q) {
    return (
      (t = new Yy(t, e, n, h, z, D, N, q, g)),
      (e = 1),
      o === !0 && (e |= 24),
      (o = we(3, null, null, e)),
      (t.current = o),
      (o.stateNode = t),
      (e = jr()),
      e.refCount++,
      (t.pooledCache = e),
      e.refCount++,
      (o.memoizedState = { element: l, isDehydrated: n, cache: e }),
      Yr(o),
      t
    );
  }
  function Yd(t) {
    return t ? ((t = Hl), t) : Hl;
  }
  function Gd(t, e, n, l, a, o) {
    ((a = Yd(a)),
      l.context === null ? (l.context = a) : (l.pendingContext = a),
      (l = jn(e)),
      (l.payload = { element: n }),
      (o = o === void 0 ? null : o),
      o !== null && (l.callback = o),
      (n = Hn(t, l, e)),
      n !== null && (Ce(n, t, e), Bi(n, t, e)));
  }
  function Xd(t, e) {
    if (((t = t.memoizedState), t !== null && t.dehydrated !== null)) {
      var n = t.retryLane;
      t.retryLane = n !== 0 && n < e ? n : e;
    }
  }
  function ao(t, e) {
    (Xd(t, e), (t = t.alternate) && Xd(t, e));
  }
  function Qd(t) {
    if (t.tag === 13 || t.tag === 31) {
      var e = rl(t, 67108864);
      (e !== null && Ce(e, t, 67108864), ao(t, 67108864));
    }
  }
  function Vd(t) {
    if (t.tag === 13 || t.tag === 31) {
      var e = je();
      e = tr(e);
      var n = rl(t, e);
      (n !== null && Ce(n, t, e), ao(t, e));
    }
  }
  var wu = !0;
  function Gy(t, e, n, l) {
    var a = M.T;
    M.T = null;
    var o = B.p;
    try {
      ((B.p = 2), uo(t, e, n, l));
    } finally {
      ((B.p = o), (M.T = a));
    }
  }
  function Xy(t, e, n, l) {
    var a = M.T;
    M.T = null;
    var o = B.p;
    try {
      ((B.p = 8), uo(t, e, n, l));
    } finally {
      ((B.p = o), (M.T = a));
    }
  }
  function uo(t, e, n, l) {
    if (wu) {
      var a = ro(l);
      if (a === null) (Zc(t, e, l, Nu, n), Kd(t, l));
      else if (Vy(a, t, e, n, l)) l.stopPropagation();
      else if ((Kd(t, l), e & 4 && -1 < Qy.indexOf(t))) {
        for (; a !== null; ) {
          var o = _l(a);
          if (o !== null)
            switch (o.tag) {
              case 3:
                if (((o = o.stateNode), o.current.memoizedState.isDehydrated)) {
                  var h = nl(o.pendingLanes);
                  if (h !== 0) {
                    var g = o;
                    for (g.pendingLanes |= 2, g.entangledLanes |= 2; h; ) {
                      var z = 1 << (31 - Gt(h));
                      ((g.entanglements[1] |= z), (h &= ~z));
                    }
                    (an(o), (Rt & 6) === 0 && ((mu = ge() + 500), $i(0)));
                  }
                }
                break;
              case 31:
              case 13:
                ((g = rl(o, 2)), g !== null && Ce(g, o, 2), yu(), ao(o, 2));
            }
          if (((o = ro(l)), o === null && Zc(t, e, l, Nu, n), o === a)) break;
          a = o;
        }
        a !== null && l.stopPropagation();
      } else Zc(t, e, l, null, n);
    }
  }
  function ro(t) {
    return ((t = or(t)), co(t));
  }
  var Nu = null;
  function co(t) {
    if (((Nu = null), (t = Cl(t)), t !== null)) {
      var e = s(t);
      if (e === null) t = null;
      else {
        var n = e.tag;
        if (n === 13) {
          if (((t = d(e)), t !== null)) return t;
          t = null;
        } else if (n === 31) {
          if (((t = m(e)), t !== null)) return t;
          t = null;
        } else if (n === 3) {
          if (e.stateNode.current.memoizedState.isDehydrated)
            return e.tag === 3 ? e.stateNode.containerInfo : null;
          t = null;
        } else e !== t && (t = null);
      }
    }
    return ((Nu = t), null);
  }
  function Zd(t) {
    switch (t) {
      case "beforetoggle":
      case "cancel":
      case "click":
      case "close":
      case "contextmenu":
      case "copy":
      case "cut":
      case "auxclick":
      case "dblclick":
      case "dragend":
      case "dragstart":
      case "drop":
      case "focusin":
      case "focusout":
      case "input":
      case "invalid":
      case "keydown":
      case "keypress":
      case "keyup":
      case "mousedown":
      case "mouseup":
      case "paste":
      case "pause":
      case "play":
      case "pointercancel":
      case "pointerdown":
      case "pointerup":
      case "ratechange":
      case "reset":
      case "resize":
      case "seeked":
      case "submit":
      case "toggle":
      case "touchcancel":
      case "touchend":
      case "touchstart":
      case "volumechange":
      case "change":
      case "selectionchange":
      case "textInput":
      case "compositionstart":
      case "compositionend":
      case "compositionupdate":
      case "beforeblur":
      case "afterblur":
      case "beforeinput":
      case "blur":
      case "fullscreenchange":
      case "focus":
      case "hashchange":
      case "popstate":
      case "select":
      case "selectstart":
        return 2;
      case "drag":
      case "dragenter":
      case "dragexit":
      case "dragleave":
      case "dragover":
      case "mousemove":
      case "mouseout":
      case "mouseover":
      case "pointermove":
      case "pointerout":
      case "pointerover":
      case "scroll":
      case "touchmove":
      case "wheel":
      case "mouseenter":
      case "mouseleave":
      case "pointerenter":
      case "pointerleave":
        return 8;
      case "message":
        switch ($u()) {
          case j:
            return 2;
          case J:
            return 8;
          case ft:
          case Tt:
            return 32;
          case Bt:
            return 268435456;
          default:
            return 32;
        }
      default:
        return 32;
    }
  }
  var oo = !1,
    Fn = null,
    In = null,
    Wn = null,
    aa = new Map(),
    ua = new Map(),
    $n = [],
    Qy =
      "mousedown mouseup touchcancel touchend touchstart auxclick dblclick pointercancel pointerdown pointerup dragend dragstart drop compositionend compositionstart keydown keypress keyup input textInput copy cut paste click change contextmenu reset".split(
        " ",
      );
  function Kd(t, e) {
    switch (t) {
      case "focusin":
      case "focusout":
        Fn = null;
        break;
      case "dragenter":
      case "dragleave":
        In = null;
        break;
      case "mouseover":
      case "mouseout":
        Wn = null;
        break;
      case "pointerover":
      case "pointerout":
        aa.delete(e.pointerId);
        break;
      case "gotpointercapture":
      case "lostpointercapture":
        ua.delete(e.pointerId);
    }
  }
  function ra(t, e, n, l, a, o) {
    return t === null || t.nativeEvent !== o
      ? ((t = {
          blockedOn: e,
          domEventName: n,
          eventSystemFlags: l,
          nativeEvent: o,
          targetContainers: [a],
        }),
        e !== null && ((e = _l(e)), e !== null && Qd(e)),
        t)
      : ((t.eventSystemFlags |= l),
        (e = t.targetContainers),
        a !== null && e.indexOf(a) === -1 && e.push(a),
        t);
  }
  function Vy(t, e, n, l, a) {
    switch (e) {
      case "focusin":
        return ((Fn = ra(Fn, t, e, n, l, a)), !0);
      case "dragenter":
        return ((In = ra(In, t, e, n, l, a)), !0);
      case "mouseover":
        return ((Wn = ra(Wn, t, e, n, l, a)), !0);
      case "pointerover":
        var o = a.pointerId;
        return (aa.set(o, ra(aa.get(o) || null, t, e, n, l, a)), !0);
      case "gotpointercapture":
        return (
          (o = a.pointerId),
          ua.set(o, ra(ua.get(o) || null, t, e, n, l, a)),
          !0
        );
    }
    return !1;
  }
  function Jd(t) {
    var e = Cl(t.target);
    if (e !== null) {
      var n = s(e);
      if (n !== null) {
        if (((e = n.tag), e === 13)) {
          if (((e = d(n)), e !== null)) {
            ((t.blockedOn = e),
              cf(t.priority, function () {
                Vd(n);
              }));
            return;
          }
        } else if (e === 31) {
          if (((e = m(n)), e !== null)) {
            ((t.blockedOn = e),
              cf(t.priority, function () {
                Vd(n);
              }));
            return;
          }
        } else if (e === 3 && n.stateNode.current.memoizedState.isDehydrated) {
          t.blockedOn = n.tag === 3 ? n.stateNode.containerInfo : null;
          return;
        }
      }
    }
    t.blockedOn = null;
  }
  function Ru(t) {
    if (t.blockedOn !== null) return !1;
    for (var e = t.targetContainers; 0 < e.length; ) {
      var n = ro(t.nativeEvent);
      if (n === null) {
        n = t.nativeEvent;
        var l = new n.constructor(n.type, n);
        ((cr = l), n.target.dispatchEvent(l), (cr = null));
      } else return ((e = _l(n)), e !== null && Qd(e), (t.blockedOn = n), !1);
      e.shift();
    }
    return !0;
  }
  function Fd(t, e, n) {
    Ru(t) && n.delete(e);
  }
  function Zy() {
    ((oo = !1),
      Fn !== null && Ru(Fn) && (Fn = null),
      In !== null && Ru(In) && (In = null),
      Wn !== null && Ru(Wn) && (Wn = null),
      aa.forEach(Fd),
      ua.forEach(Fd));
  }
  function Uu(t, e) {
    t.blockedOn === e &&
      ((t.blockedOn = null),
      oo ||
        ((oo = !0),
        i.unstable_scheduleCallback(i.unstable_NormalPriority, Zy)));
  }
  var Bu = null;
  function Id(t) {
    Bu !== t &&
      ((Bu = t),
      i.unstable_scheduleCallback(i.unstable_NormalPriority, function () {
        Bu === t && (Bu = null);
        for (var e = 0; e < t.length; e += 3) {
          var n = t[e],
            l = t[e + 1],
            a = t[e + 2];
          if (typeof l != "function") {
            if (co(l || n) === null) continue;
            break;
          }
          var o = _l(n);
          o !== null &&
            (t.splice(e, 3),
            (e -= 3),
            rc(o, { pending: !0, data: a, method: n.method, action: l }, l, a));
        }
      }));
  }
  function ci(t) {
    function e(z) {
      return Uu(z, t);
    }
    (Fn !== null && Uu(Fn, t),
      In !== null && Uu(In, t),
      Wn !== null && Uu(Wn, t),
      aa.forEach(e),
      ua.forEach(e));
    for (var n = 0; n < $n.length; n++) {
      var l = $n[n];
      l.blockedOn === t && (l.blockedOn = null);
    }
    for (; 0 < $n.length && ((n = $n[0]), n.blockedOn === null); )
      (Jd(n), n.blockedOn === null && $n.shift());
    if (((n = (t.ownerDocument || t).$$reactFormReplay), n != null))
      for (l = 0; l < n.length; l += 3) {
        var a = n[l],
          o = n[l + 1],
          h = a[Se] || null;
        if (typeof o == "function") h || Id(n);
        else if (h) {
          var g = null;
          if (o && o.hasAttribute("formAction")) {
            if (((a = o), (h = o[Se] || null))) g = h.formAction;
            else if (co(a) !== null) continue;
          } else g = h.action;
          (typeof g == "function" ? (n[l + 1] = g) : (n.splice(l, 3), (l -= 3)),
            Id(n));
        }
      }
  }
  function Wd() {
    function t(o) {
      o.canIntercept &&
        o.info === "react-transition" &&
        o.intercept({
          handler: function () {
            return new Promise(function (h) {
              return (a = h);
            });
          },
          focusReset: "manual",
          scroll: "manual",
        });
    }
    function e() {
      (a !== null && (a(), (a = null)), l || setTimeout(n, 20));
    }
    function n() {
      if (!l && !navigation.transition) {
        var o = navigation.currentEntry;
        o &&
          o.url != null &&
          navigation.navigate(o.url, {
            state: o.getState(),
            info: "react-transition",
            history: "replace",
          });
      }
    }
    if (typeof navigation == "object") {
      var l = !1,
        a = null;
      return (
        navigation.addEventListener("navigate", t),
        navigation.addEventListener("navigatesuccess", e),
        navigation.addEventListener("navigateerror", e),
        setTimeout(n, 100),
        function () {
          ((l = !0),
            navigation.removeEventListener("navigate", t),
            navigation.removeEventListener("navigatesuccess", e),
            navigation.removeEventListener("navigateerror", e),
            a !== null && (a(), (a = null)));
        }
      );
    }
  }
  function fo(t) {
    this._internalRoot = t;
  }
  ((ju.prototype.render = fo.prototype.render =
    function (t) {
      var e = this._internalRoot;
      if (e === null) throw Error(c(409));
      var n = e.current,
        l = je();
      Gd(n, l, t, e, null, null);
    }),
    (ju.prototype.unmount = fo.prototype.unmount =
      function () {
        var t = this._internalRoot;
        if (t !== null) {
          this._internalRoot = null;
          var e = t.containerInfo;
          (Gd(t.current, 2, null, t, null, null), yu(), (e[Al] = null));
        }
      }));
  function ju(t) {
    this._internalRoot = t;
  }
  ju.prototype.unstable_scheduleHydration = function (t) {
    if (t) {
      var e = rf();
      t = { blockedOn: null, target: t, priority: e };
      for (var n = 0; n < $n.length && e !== 0 && e < $n[n].priority; n++);
      ($n.splice(n, 0, t), n === 0 && Jd(t));
    }
  };
  var $d = u.version;
  if ($d !== "19.2.3") throw Error(c(527, $d, "19.2.3"));
  B.findDOMNode = function (t) {
    var e = t._reactInternals;
    if (e === void 0)
      throw typeof t.render == "function"
        ? Error(c(188))
        : ((t = Object.keys(t).join(",")), Error(c(268, t)));
    return (
      (t = p(e)),
      (t = t !== null ? b(t) : null),
      (t = t === null ? null : t.stateNode),
      t
    );
  };
  var Ky = {
    bundleType: 0,
    version: "19.2.3",
    rendererPackageName: "react-dom",
    currentDispatcherRef: M,
    reconcilerVersion: "19.2.3",
  };
  if (typeof __REACT_DEVTOOLS_GLOBAL_HOOK__ < "u") {
    var Hu = __REACT_DEVTOOLS_GLOBAL_HOOK__;
    if (!Hu.isDisabled && Hu.supportsFiber)
      try {
        ((ye = Hu.inject(Ky)), (ie = Hu));
      } catch {}
  }
  return (
    (oa.createRoot = function (t, e) {
      if (!f(t)) throw Error(c(299));
      var n = !1,
        l = "",
        a = ah,
        o = uh,
        h = rh;
      return (
        e != null &&
          (e.unstable_strictMode === !0 && (n = !0),
          e.identifierPrefix !== void 0 && (l = e.identifierPrefix),
          e.onUncaughtError !== void 0 && (a = e.onUncaughtError),
          e.onCaughtError !== void 0 && (o = e.onCaughtError),
          e.onRecoverableError !== void 0 && (h = e.onRecoverableError)),
        (e = qd(t, 1, !1, null, null, n, l, null, a, o, h, Wd)),
        (t[Al] = e.current),
        Vc(t),
        new fo(e)
      );
    }),
    (oa.hydrateRoot = function (t, e, n) {
      if (!f(t)) throw Error(c(299));
      var l = !1,
        a = "",
        o = ah,
        h = uh,
        g = rh,
        z = null;
      return (
        n != null &&
          (n.unstable_strictMode === !0 && (l = !0),
          n.identifierPrefix !== void 0 && (a = n.identifierPrefix),
          n.onUncaughtError !== void 0 && (o = n.onUncaughtError),
          n.onCaughtError !== void 0 && (h = n.onCaughtError),
          n.onRecoverableError !== void 0 && (g = n.onRecoverableError),
          n.formState !== void 0 && (z = n.formState)),
        (e = qd(t, 1, !0, e, n ?? null, l, a, z, o, h, g, Wd)),
        (e.context = Yd(null)),
        (n = e.current),
        (l = je()),
        (l = tr(l)),
        (a = jn(l)),
        (a.callback = null),
        Hn(n, a, l),
        (n = l),
        (e.current.lanes = n),
        bi(e, n),
        an(e),
        (t[Al] = e.current),
        Vc(t),
        new ju(e)
      );
    }),
    (oa.version = "19.2.3"),
    oa
  );
}
var cp;
function l1() {
  if (cp) return po.exports;
  cp = 1;
  function i() {
    if (
      !(
        typeof __REACT_DEVTOOLS_GLOBAL_HOOK__ > "u" ||
        typeof __REACT_DEVTOOLS_GLOBAL_HOOK__.checkDCE != "function"
      )
    )
      try {
        __REACT_DEVTOOLS_GLOBAL_HOOK__.checkDCE(i);
      } catch (u) {
        console.error(u);
      }
  }
  return (i(), (po.exports = n1()), po.exports);
}
var i1 = l1();
function a1(i, u) {
  const r = {};
  return (i[i.length - 1] === "" ? [...i, ""] : i)
    .join((r.padRight ? " " : "") + "," + (r.padLeft === !1 ? "" : " "))
    .trim();
}
const u1 = /^[$_\p{ID_Start}][$_\u{200C}\u{200D}\p{ID_Continue}]*$/u,
  r1 = /^[$_\p{ID_Start}][-$_\u{200C}\u{200D}\p{ID_Continue}]*$/u,
  c1 = {};
function op(i, u) {
  return (c1.jsx ? r1 : u1).test(i);
}
const o1 = /[ \t\n\f\r]/g;
function f1(i) {
  return typeof i == "object" ? (i.type === "text" ? fp(i.value) : !1) : fp(i);
}
function fp(i) {
  return i.replace(o1, "") === "";
}
class ba {
  constructor(u, r, c) {
    ((this.normal = r), (this.property = u), c && (this.space = c));
  }
}
ba.prototype.normal = {};
ba.prototype.property = {};
ba.prototype.space = void 0;
function Fp(i, u) {
  const r = {},
    c = {};
  for (const f of i) (Object.assign(r, f.property), Object.assign(c, f.normal));
  return new ba(r, c, u);
}
function ko(i) {
  return i.toLowerCase();
}
class De {
  constructor(u, r) {
    ((this.attribute = r), (this.property = u));
  }
}
De.prototype.attribute = "";
De.prototype.booleanish = !1;
De.prototype.boolean = !1;
De.prototype.commaOrSpaceSeparated = !1;
De.prototype.commaSeparated = !1;
De.prototype.defined = !1;
De.prototype.mustUseProperty = !1;
De.prototype.number = !1;
De.prototype.overloadedBoolean = !1;
De.prototype.property = "";
De.prototype.spaceSeparated = !1;
De.prototype.space = void 0;
let s1 = 0;
const vt = Sl(),
  le = Sl(),
  wo = Sl(),
  Z = Sl(),
  Qt = Sl(),
  si = Sl(),
  He = Sl();
function Sl() {
  return 2 ** ++s1;
}
const No = Object.freeze(
    Object.defineProperty(
      {
        __proto__: null,
        boolean: vt,
        booleanish: le,
        commaOrSpaceSeparated: He,
        commaSeparated: si,
        number: Z,
        overloadedBoolean: wo,
        spaceSeparated: Qt,
      },
      Symbol.toStringTag,
      { value: "Module" },
    ),
  ),
  bo = Object.keys(No);
class Go extends De {
  constructor(u, r, c, f) {
    let s = -1;
    if ((super(u, r), sp(this, "space", f), typeof c == "number"))
      for (; ++s < bo.length; ) {
        const d = bo[s];
        sp(this, bo[s], (c & No[d]) === No[d]);
      }
  }
}
Go.prototype.defined = !0;
function sp(i, u, r) {
  r && (i[u] = r);
}
function di(i) {
  const u = {},
    r = {};
  for (const [c, f] of Object.entries(i.properties)) {
    const s = new Go(c, i.transform(i.attributes || {}, c), f, i.space);
    (i.mustUseProperty &&
      i.mustUseProperty.includes(c) &&
      (s.mustUseProperty = !0),
      (u[c] = s),
      (r[ko(c)] = c),
      (r[ko(s.attribute)] = c));
  }
  return new ba(u, r, i.space);
}
const Ip = di({
  properties: {
    ariaActiveDescendant: null,
    ariaAtomic: le,
    ariaAutoComplete: null,
    ariaBusy: le,
    ariaChecked: le,
    ariaColCount: Z,
    ariaColIndex: Z,
    ariaColSpan: Z,
    ariaControls: Qt,
    ariaCurrent: null,
    ariaDescribedBy: Qt,
    ariaDetails: null,
    ariaDisabled: le,
    ariaDropEffect: Qt,
    ariaErrorMessage: null,
    ariaExpanded: le,
    ariaFlowTo: Qt,
    ariaGrabbed: le,
    ariaHasPopup: null,
    ariaHidden: le,
    ariaInvalid: null,
    ariaKeyShortcuts: null,
    ariaLabel: null,
    ariaLabelledBy: Qt,
    ariaLevel: Z,
    ariaLive: null,
    ariaModal: le,
    ariaMultiLine: le,
    ariaMultiSelectable: le,
    ariaOrientation: null,
    ariaOwns: Qt,
    ariaPlaceholder: null,
    ariaPosInSet: Z,
    ariaPressed: le,
    ariaReadOnly: le,
    ariaRelevant: null,
    ariaRequired: le,
    ariaRoleDescription: Qt,
    ariaRowCount: Z,
    ariaRowIndex: Z,
    ariaRowSpan: Z,
    ariaSelected: le,
    ariaSetSize: Z,
    ariaSort: null,
    ariaValueMax: Z,
    ariaValueMin: Z,
    ariaValueNow: Z,
    ariaValueText: null,
    role: null,
  },
  transform(i, u) {
    return u === "role" ? u : "aria-" + u.slice(4).toLowerCase();
  },
});
function Wp(i, u) {
  return u in i ? i[u] : u;
}
function $p(i, u) {
  return Wp(i, u.toLowerCase());
}
const h1 = di({
    attributes: {
      acceptcharset: "accept-charset",
      classname: "class",
      htmlfor: "for",
      httpequiv: "http-equiv",
    },
    mustUseProperty: ["checked", "multiple", "muted", "selected"],
    properties: {
      abbr: null,
      accept: si,
      acceptCharset: Qt,
      accessKey: Qt,
      action: null,
      allow: null,
      allowFullScreen: vt,
      allowPaymentRequest: vt,
      allowUserMedia: vt,
      alt: null,
      as: null,
      async: vt,
      autoCapitalize: null,
      autoComplete: Qt,
      autoFocus: vt,
      autoPlay: vt,
      blocking: Qt,
      capture: null,
      charSet: null,
      checked: vt,
      cite: null,
      className: Qt,
      cols: Z,
      colSpan: null,
      content: null,
      contentEditable: le,
      controls: vt,
      controlsList: Qt,
      coords: Z | si,
      crossOrigin: null,
      data: null,
      dateTime: null,
      decoding: null,
      default: vt,
      defer: vt,
      dir: null,
      dirName: null,
      disabled: vt,
      download: wo,
      draggable: le,
      encType: null,
      enterKeyHint: null,
      fetchPriority: null,
      form: null,
      formAction: null,
      formEncType: null,
      formMethod: null,
      formNoValidate: vt,
      formTarget: null,
      headers: Qt,
      height: Z,
      hidden: wo,
      high: Z,
      href: null,
      hrefLang: null,
      htmlFor: Qt,
      httpEquiv: Qt,
      id: null,
      imageSizes: null,
      imageSrcSet: null,
      inert: vt,
      inputMode: null,
      integrity: null,
      is: null,
      isMap: vt,
      itemId: null,
      itemProp: Qt,
      itemRef: Qt,
      itemScope: vt,
      itemType: Qt,
      kind: null,
      label: null,
      lang: null,
      language: null,
      list: null,
      loading: null,
      loop: vt,
      low: Z,
      manifest: null,
      max: null,
      maxLength: Z,
      media: null,
      method: null,
      min: null,
      minLength: Z,
      multiple: vt,
      muted: vt,
      name: null,
      nonce: null,
      noModule: vt,
      noValidate: vt,
      onAbort: null,
      onAfterPrint: null,
      onAuxClick: null,
      onBeforeMatch: null,
      onBeforePrint: null,
      onBeforeToggle: null,
      onBeforeUnload: null,
      onBlur: null,
      onCancel: null,
      onCanPlay: null,
      onCanPlayThrough: null,
      onChange: null,
      onClick: null,
      onClose: null,
      onContextLost: null,
      onContextMenu: null,
      onContextRestored: null,
      onCopy: null,
      onCueChange: null,
      onCut: null,
      onDblClick: null,
      onDrag: null,
      onDragEnd: null,
      onDragEnter: null,
      onDragExit: null,
      onDragLeave: null,
      onDragOver: null,
      onDragStart: null,
      onDrop: null,
      onDurationChange: null,
      onEmptied: null,
      onEnded: null,
      onError: null,
      onFocus: null,
      onFormData: null,
      onHashChange: null,
      onInput: null,
      onInvalid: null,
      onKeyDown: null,
      onKeyPress: null,
      onKeyUp: null,
      onLanguageChange: null,
      onLoad: null,
      onLoadedData: null,
      onLoadedMetadata: null,
      onLoadEnd: null,
      onLoadStart: null,
      onMessage: null,
      onMessageError: null,
      onMouseDown: null,
      onMouseEnter: null,
      onMouseLeave: null,
      onMouseMove: null,
      onMouseOut: null,
      onMouseOver: null,
      onMouseUp: null,
      onOffline: null,
      onOnline: null,
      onPageHide: null,
      onPageShow: null,
      onPaste: null,
      onPause: null,
      onPlay: null,
      onPlaying: null,
      onPopState: null,
      onProgress: null,
      onRateChange: null,
      onRejectionHandled: null,
      onReset: null,
      onResize: null,
      onScroll: null,
      onScrollEnd: null,
      onSecurityPolicyViolation: null,
      onSeeked: null,
      onSeeking: null,
      onSelect: null,
      onSlotChange: null,
      onStalled: null,
      onStorage: null,
      onSubmit: null,
      onSuspend: null,
      onTimeUpdate: null,
      onToggle: null,
      onUnhandledRejection: null,
      onUnload: null,
      onVolumeChange: null,
      onWaiting: null,
      onWheel: null,
      open: vt,
      optimum: Z,
      pattern: null,
      ping: Qt,
      placeholder: null,
      playsInline: vt,
      popover: null,
      popoverTarget: null,
      popoverTargetAction: null,
      poster: null,
      preload: null,
      readOnly: vt,
      referrerPolicy: null,
      rel: Qt,
      required: vt,
      reversed: vt,
      rows: Z,
      rowSpan: Z,
      sandbox: Qt,
      scope: null,
      scoped: vt,
      seamless: vt,
      selected: vt,
      shadowRootClonable: vt,
      shadowRootDelegatesFocus: vt,
      shadowRootMode: null,
      shape: null,
      size: Z,
      sizes: null,
      slot: null,
      span: Z,
      spellCheck: le,
      src: null,
      srcDoc: null,
      srcLang: null,
      srcSet: null,
      start: Z,
      step: null,
      style: null,
      tabIndex: Z,
      target: null,
      title: null,
      translate: null,
      type: null,
      typeMustMatch: vt,
      useMap: null,
      value: le,
      width: Z,
      wrap: null,
      writingSuggestions: null,
      align: null,
      aLink: null,
      archive: Qt,
      axis: null,
      background: null,
      bgColor: null,
      border: Z,
      borderColor: null,
      bottomMargin: Z,
      cellPadding: null,
      cellSpacing: null,
      char: null,
      charOff: null,
      classId: null,
      clear: null,
      code: null,
      codeBase: null,
      codeType: null,
      color: null,
      compact: vt,
      declare: vt,
      event: null,
      face: null,
      frame: null,
      frameBorder: null,
      hSpace: Z,
      leftMargin: Z,
      link: null,
      longDesc: null,
      lowSrc: null,
      marginHeight: Z,
      marginWidth: Z,
      noResize: vt,
      noHref: vt,
      noShade: vt,
      noWrap: vt,
      object: null,
      profile: null,
      prompt: null,
      rev: null,
      rightMargin: Z,
      rules: null,
      scheme: null,
      scrolling: le,
      standby: null,
      summary: null,
      text: null,
      topMargin: Z,
      valueType: null,
      version: null,
      vAlign: null,
      vLink: null,
      vSpace: Z,
      allowTransparency: null,
      autoCorrect: null,
      autoSave: null,
      disablePictureInPicture: vt,
      disableRemotePlayback: vt,
      prefix: null,
      property: null,
      results: Z,
      security: null,
      unselectable: null,
    },
    space: "html",
    transform: $p,
  }),
  d1 = di({
    attributes: {
      accentHeight: "accent-height",
      alignmentBaseline: "alignment-baseline",
      arabicForm: "arabic-form",
      baselineShift: "baseline-shift",
      capHeight: "cap-height",
      className: "class",
      clipPath: "clip-path",
      clipRule: "clip-rule",
      colorInterpolation: "color-interpolation",
      colorInterpolationFilters: "color-interpolation-filters",
      colorProfile: "color-profile",
      colorRendering: "color-rendering",
      crossOrigin: "crossorigin",
      dataType: "datatype",
      dominantBaseline: "dominant-baseline",
      enableBackground: "enable-background",
      fillOpacity: "fill-opacity",
      fillRule: "fill-rule",
      floodColor: "flood-color",
      floodOpacity: "flood-opacity",
      fontFamily: "font-family",
      fontSize: "font-size",
      fontSizeAdjust: "font-size-adjust",
      fontStretch: "font-stretch",
      fontStyle: "font-style",
      fontVariant: "font-variant",
      fontWeight: "font-weight",
      glyphName: "glyph-name",
      glyphOrientationHorizontal: "glyph-orientation-horizontal",
      glyphOrientationVertical: "glyph-orientation-vertical",
      hrefLang: "hreflang",
      horizAdvX: "horiz-adv-x",
      horizOriginX: "horiz-origin-x",
      horizOriginY: "horiz-origin-y",
      imageRendering: "image-rendering",
      letterSpacing: "letter-spacing",
      lightingColor: "lighting-color",
      markerEnd: "marker-end",
      markerMid: "marker-mid",
      markerStart: "marker-start",
      navDown: "nav-down",
      navDownLeft: "nav-down-left",
      navDownRight: "nav-down-right",
      navLeft: "nav-left",
      navNext: "nav-next",
      navPrev: "nav-prev",
      navRight: "nav-right",
      navUp: "nav-up",
      navUpLeft: "nav-up-left",
      navUpRight: "nav-up-right",
      onAbort: "onabort",
      onActivate: "onactivate",
      onAfterPrint: "onafterprint",
      onBeforePrint: "onbeforeprint",
      onBegin: "onbegin",
      onCancel: "oncancel",
      onCanPlay: "oncanplay",
      onCanPlayThrough: "oncanplaythrough",
      onChange: "onchange",
      onClick: "onclick",
      onClose: "onclose",
      onCopy: "oncopy",
      onCueChange: "oncuechange",
      onCut: "oncut",
      onDblClick: "ondblclick",
      onDrag: "ondrag",
      onDragEnd: "ondragend",
      onDragEnter: "ondragenter",
      onDragExit: "ondragexit",
      onDragLeave: "ondragleave",
      onDragOver: "ondragover",
      onDragStart: "ondragstart",
      onDrop: "ondrop",
      onDurationChange: "ondurationchange",
      onEmptied: "onemptied",
      onEnd: "onend",
      onEnded: "onended",
      onError: "onerror",
      onFocus: "onfocus",
      onFocusIn: "onfocusin",
      onFocusOut: "onfocusout",
      onHashChange: "onhashchange",
      onInput: "oninput",
      onInvalid: "oninvalid",
      onKeyDown: "onkeydown",
      onKeyPress: "onkeypress",
      onKeyUp: "onkeyup",
      onLoad: "onload",
      onLoadedData: "onloadeddata",
      onLoadedMetadata: "onloadedmetadata",
      onLoadStart: "onloadstart",
      onMessage: "onmessage",
      onMouseDown: "onmousedown",
      onMouseEnter: "onmouseenter",
      onMouseLeave: "onmouseleave",
      onMouseMove: "onmousemove",
      onMouseOut: "onmouseout",
      onMouseOver: "onmouseover",
      onMouseUp: "onmouseup",
      onMouseWheel: "onmousewheel",
      onOffline: "onoffline",
      onOnline: "ononline",
      onPageHide: "onpagehide",
      onPageShow: "onpageshow",
      onPaste: "onpaste",
      onPause: "onpause",
      onPlay: "onplay",
      onPlaying: "onplaying",
      onPopState: "onpopstate",
      onProgress: "onprogress",
      onRateChange: "onratechange",
      onRepeat: "onrepeat",
      onReset: "onreset",
      onResize: "onresize",
      onScroll: "onscroll",
      onSeeked: "onseeked",
      onSeeking: "onseeking",
      onSelect: "onselect",
      onShow: "onshow",
      onStalled: "onstalled",
      onStorage: "onstorage",
      onSubmit: "onsubmit",
      onSuspend: "onsuspend",
      onTimeUpdate: "ontimeupdate",
      onToggle: "ontoggle",
      onUnload: "onunload",
      onVolumeChange: "onvolumechange",
      onWaiting: "onwaiting",
      onZoom: "onzoom",
      overlinePosition: "overline-position",
      overlineThickness: "overline-thickness",
      paintOrder: "paint-order",
      panose1: "panose-1",
      pointerEvents: "pointer-events",
      referrerPolicy: "referrerpolicy",
      renderingIntent: "rendering-intent",
      shapeRendering: "shape-rendering",
      stopColor: "stop-color",
      stopOpacity: "stop-opacity",
      strikethroughPosition: "strikethrough-position",
      strikethroughThickness: "strikethrough-thickness",
      strokeDashArray: "stroke-dasharray",
      strokeDashOffset: "stroke-dashoffset",
      strokeLineCap: "stroke-linecap",
      strokeLineJoin: "stroke-linejoin",
      strokeMiterLimit: "stroke-miterlimit",
      strokeOpacity: "stroke-opacity",
      strokeWidth: "stroke-width",
      tabIndex: "tabindex",
      textAnchor: "text-anchor",
      textDecoration: "text-decoration",
      textRendering: "text-rendering",
      transformOrigin: "transform-origin",
      typeOf: "typeof",
      underlinePosition: "underline-position",
      underlineThickness: "underline-thickness",
      unicodeBidi: "unicode-bidi",
      unicodeRange: "unicode-range",
      unitsPerEm: "units-per-em",
      vAlphabetic: "v-alphabetic",
      vHanging: "v-hanging",
      vIdeographic: "v-ideographic",
      vMathematical: "v-mathematical",
      vectorEffect: "vector-effect",
      vertAdvY: "vert-adv-y",
      vertOriginX: "vert-origin-x",
      vertOriginY: "vert-origin-y",
      wordSpacing: "word-spacing",
      writingMode: "writing-mode",
      xHeight: "x-height",
      playbackOrder: "playbackorder",
      timelineBegin: "timelinebegin",
    },
    properties: {
      about: He,
      accentHeight: Z,
      accumulate: null,
      additive: null,
      alignmentBaseline: null,
      alphabetic: Z,
      amplitude: Z,
      arabicForm: null,
      ascent: Z,
      attributeName: null,
      attributeType: null,
      azimuth: Z,
      bandwidth: null,
      baselineShift: null,
      baseFrequency: null,
      baseProfile: null,
      bbox: null,
      begin: null,
      bias: Z,
      by: null,
      calcMode: null,
      capHeight: Z,
      className: Qt,
      clip: null,
      clipPath: null,
      clipPathUnits: null,
      clipRule: null,
      color: null,
      colorInterpolation: null,
      colorInterpolationFilters: null,
      colorProfile: null,
      colorRendering: null,
      content: null,
      contentScriptType: null,
      contentStyleType: null,
      crossOrigin: null,
      cursor: null,
      cx: null,
      cy: null,
      d: null,
      dataType: null,
      defaultAction: null,
      descent: Z,
      diffuseConstant: Z,
      direction: null,
      display: null,
      dur: null,
      divisor: Z,
      dominantBaseline: null,
      download: vt,
      dx: null,
      dy: null,
      edgeMode: null,
      editable: null,
      elevation: Z,
      enableBackground: null,
      end: null,
      event: null,
      exponent: Z,
      externalResourcesRequired: null,
      fill: null,
      fillOpacity: Z,
      fillRule: null,
      filter: null,
      filterRes: null,
      filterUnits: null,
      floodColor: null,
      floodOpacity: null,
      focusable: null,
      focusHighlight: null,
      fontFamily: null,
      fontSize: null,
      fontSizeAdjust: null,
      fontStretch: null,
      fontStyle: null,
      fontVariant: null,
      fontWeight: null,
      format: null,
      fr: null,
      from: null,
      fx: null,
      fy: null,
      g1: si,
      g2: si,
      glyphName: si,
      glyphOrientationHorizontal: null,
      glyphOrientationVertical: null,
      glyphRef: null,
      gradientTransform: null,
      gradientUnits: null,
      handler: null,
      hanging: Z,
      hatchContentUnits: null,
      hatchUnits: null,
      height: null,
      href: null,
      hrefLang: null,
      horizAdvX: Z,
      horizOriginX: Z,
      horizOriginY: Z,
      id: null,
      ideographic: Z,
      imageRendering: null,
      initialVisibility: null,
      in: null,
      in2: null,
      intercept: Z,
      k: Z,
      k1: Z,
      k2: Z,
      k3: Z,
      k4: Z,
      kernelMatrix: He,
      kernelUnitLength: null,
      keyPoints: null,
      keySplines: null,
      keyTimes: null,
      kerning: null,
      lang: null,
      lengthAdjust: null,
      letterSpacing: null,
      lightingColor: null,
      limitingConeAngle: Z,
      local: null,
      markerEnd: null,
      markerMid: null,
      markerStart: null,
      markerHeight: null,
      markerUnits: null,
      markerWidth: null,
      mask: null,
      maskContentUnits: null,
      maskUnits: null,
      mathematical: null,
      max: null,
      media: null,
      mediaCharacterEncoding: null,
      mediaContentEncodings: null,
      mediaSize: Z,
      mediaTime: null,
      method: null,
      min: null,
      mode: null,
      name: null,
      navDown: null,
      navDownLeft: null,
      navDownRight: null,
      navLeft: null,
      navNext: null,
      navPrev: null,
      navRight: null,
      navUp: null,
      navUpLeft: null,
      navUpRight: null,
      numOctaves: null,
      observer: null,
      offset: null,
      onAbort: null,
      onActivate: null,
      onAfterPrint: null,
      onBeforePrint: null,
      onBegin: null,
      onCancel: null,
      onCanPlay: null,
      onCanPlayThrough: null,
      onChange: null,
      onClick: null,
      onClose: null,
      onCopy: null,
      onCueChange: null,
      onCut: null,
      onDblClick: null,
      onDrag: null,
      onDragEnd: null,
      onDragEnter: null,
      onDragExit: null,
      onDragLeave: null,
      onDragOver: null,
      onDragStart: null,
      onDrop: null,
      onDurationChange: null,
      onEmptied: null,
      onEnd: null,
      onEnded: null,
      onError: null,
      onFocus: null,
      onFocusIn: null,
      onFocusOut: null,
      onHashChange: null,
      onInput: null,
      onInvalid: null,
      onKeyDown: null,
      onKeyPress: null,
      onKeyUp: null,
      onLoad: null,
      onLoadedData: null,
      onLoadedMetadata: null,
      onLoadStart: null,
      onMessage: null,
      onMouseDown: null,
      onMouseEnter: null,
      onMouseLeave: null,
      onMouseMove: null,
      onMouseOut: null,
      onMouseOver: null,
      onMouseUp: null,
      onMouseWheel: null,
      onOffline: null,
      onOnline: null,
      onPageHide: null,
      onPageShow: null,
      onPaste: null,
      onPause: null,
      onPlay: null,
      onPlaying: null,
      onPopState: null,
      onProgress: null,
      onRateChange: null,
      onRepeat: null,
      onReset: null,
      onResize: null,
      onScroll: null,
      onSeeked: null,
      onSeeking: null,
      onSelect: null,
      onShow: null,
      onStalled: null,
      onStorage: null,
      onSubmit: null,
      onSuspend: null,
      onTimeUpdate: null,
      onToggle: null,
      onUnload: null,
      onVolumeChange: null,
      onWaiting: null,
      onZoom: null,
      opacity: null,
      operator: null,
      order: null,
      orient: null,
      orientation: null,
      origin: null,
      overflow: null,
      overlay: null,
      overlinePosition: Z,
      overlineThickness: Z,
      paintOrder: null,
      panose1: null,
      path: null,
      pathLength: Z,
      patternContentUnits: null,
      patternTransform: null,
      patternUnits: null,
      phase: null,
      ping: Qt,
      pitch: null,
      playbackOrder: null,
      pointerEvents: null,
      points: null,
      pointsAtX: Z,
      pointsAtY: Z,
      pointsAtZ: Z,
      preserveAlpha: null,
      preserveAspectRatio: null,
      primitiveUnits: null,
      propagate: null,
      property: He,
      r: null,
      radius: null,
      referrerPolicy: null,
      refX: null,
      refY: null,
      rel: He,
      rev: He,
      renderingIntent: null,
      repeatCount: null,
      repeatDur: null,
      requiredExtensions: He,
      requiredFeatures: He,
      requiredFonts: He,
      requiredFormats: He,
      resource: null,
      restart: null,
      result: null,
      rotate: null,
      rx: null,
      ry: null,
      scale: null,
      seed: null,
      shapeRendering: null,
      side: null,
      slope: null,
      snapshotTime: null,
      specularConstant: Z,
      specularExponent: Z,
      spreadMethod: null,
      spacing: null,
      startOffset: null,
      stdDeviation: null,
      stemh: null,
      stemv: null,
      stitchTiles: null,
      stopColor: null,
      stopOpacity: null,
      strikethroughPosition: Z,
      strikethroughThickness: Z,
      string: null,
      stroke: null,
      strokeDashArray: He,
      strokeDashOffset: null,
      strokeLineCap: null,
      strokeLineJoin: null,
      strokeMiterLimit: Z,
      strokeOpacity: Z,
      strokeWidth: null,
      style: null,
      surfaceScale: Z,
      syncBehavior: null,
      syncBehaviorDefault: null,
      syncMaster: null,
      syncTolerance: null,
      syncToleranceDefault: null,
      systemLanguage: He,
      tabIndex: Z,
      tableValues: null,
      target: null,
      targetX: Z,
      targetY: Z,
      textAnchor: null,
      textDecoration: null,
      textRendering: null,
      textLength: null,
      timelineBegin: null,
      title: null,
      transformBehavior: null,
      type: null,
      typeOf: He,
      to: null,
      transform: null,
      transformOrigin: null,
      u1: null,
      u2: null,
      underlinePosition: Z,
      underlineThickness: Z,
      unicode: null,
      unicodeBidi: null,
      unicodeRange: null,
      unitsPerEm: Z,
      values: null,
      vAlphabetic: Z,
      vMathematical: Z,
      vectorEffect: null,
      vHanging: Z,
      vIdeographic: Z,
      version: null,
      vertAdvY: Z,
      vertOriginX: Z,
      vertOriginY: Z,
      viewBox: null,
      viewTarget: null,
      visibility: null,
      width: null,
      widths: null,
      wordSpacing: null,
      writingMode: null,
      x: null,
      x1: null,
      x2: null,
      xChannelSelector: null,
      xHeight: Z,
      y: null,
      y1: null,
      y2: null,
      yChannelSelector: null,
      z: null,
      zoomAndPan: null,
    },
    space: "svg",
    transform: Wp,
  }),
  Pp = di({
    properties: {
      xLinkActuate: null,
      xLinkArcRole: null,
      xLinkHref: null,
      xLinkRole: null,
      xLinkShow: null,
      xLinkTitle: null,
      xLinkType: null,
    },
    space: "xlink",
    transform(i, u) {
      return "xlink:" + u.slice(5).toLowerCase();
    },
  }),
  tm = di({
    attributes: { xmlnsxlink: "xmlns:xlink" },
    properties: { xmlnsXLink: null, xmlns: null },
    space: "xmlns",
    transform: $p,
  }),
  em = di({
    properties: { xmlBase: null, xmlLang: null, xmlSpace: null },
    space: "xml",
    transform(i, u) {
      return "xml:" + u.slice(3).toLowerCase();
    },
  }),
  p1 = {
    classId: "classID",
    dataType: "datatype",
    itemId: "itemID",
    strokeDashArray: "strokeDasharray",
    strokeDashOffset: "strokeDashoffset",
    strokeLineCap: "strokeLinecap",
    strokeLineJoin: "strokeLinejoin",
    strokeMiterLimit: "strokeMiterlimit",
    typeOf: "typeof",
    xLinkActuate: "xlinkActuate",
    xLinkArcRole: "xlinkArcrole",
    xLinkHref: "xlinkHref",
    xLinkRole: "xlinkRole",
    xLinkShow: "xlinkShow",
    xLinkTitle: "xlinkTitle",
    xLinkType: "xlinkType",
    xmlnsXLink: "xmlnsXlink",
  },
  m1 = /[A-Z]/g,
  hp = /-[a-z]/g,
  g1 = /^data[-\w.:]+$/i;
function y1(i, u) {
  const r = ko(u);
  let c = u,
    f = De;
  if (r in i.normal) return i.property[i.normal[r]];
  if (r.length > 4 && r.slice(0, 4) === "data" && g1.test(u)) {
    if (u.charAt(4) === "-") {
      const s = u.slice(5).replace(hp, v1);
      c = "data" + s.charAt(0).toUpperCase() + s.slice(1);
    } else {
      const s = u.slice(4);
      if (!hp.test(s)) {
        let d = s.replace(m1, b1);
        (d.charAt(0) !== "-" && (d = "-" + d), (u = "data" + d));
      }
    }
    f = Go;
  }
  return new f(c, u);
}
function b1(i) {
  return "-" + i.toLowerCase();
}
function v1(i) {
  return i.charAt(1).toUpperCase();
}
const S1 = Fp([Ip, h1, Pp, tm, em], "html"),
  Xo = Fp([Ip, d1, Pp, tm, em], "svg");
function x1(i) {
  return i.join(" ").trim();
}
var oi = {},
  vo,
  dp;
function E1() {
  if (dp) return vo;
  dp = 1;
  var i = /\/\*[^*]*\*+([^/*][^*]*\*+)*\//g,
    u = /\n/g,
    r = /^\s*/,
    c = /^(\*?[-#/*\\\w]+(\[[0-9a-z_-]+\])?)\s*/,
    f = /^:\s*/,
    s = /^((?:'(?:\\'|.)*?'|"(?:\\"|.)*?"|\([^)]*?\)|[^};])+)/,
    d = /^[;\s]*/,
    m = /^\s+|\s+$/g,
    y = `
`,
    p = "/",
    b = "*",
    v = "",
    T = "comment",
    x = "declaration";
  function X(F, Y) {
    if (typeof F != "string")
      throw new TypeError("First argument must be a string");
    if (!F) return [];
    Y = Y || {};
    var it = 1,
      K = 1;
    function mt(lt) {
      var Q = lt.match(u);
      Q && (it += Q.length);
      var M = lt.lastIndexOf(y);
      K = ~M ? lt.length - M : K + lt.length;
    }
    function yt() {
      var lt = { line: it, column: K };
      return function (Q) {
        return ((Q.position = new H(lt)), pt(), Q);
      };
    }
    function H(lt) {
      ((this.start = lt),
        (this.end = { line: it, column: K }),
        (this.source = Y.source));
    }
    H.prototype.content = F;
    function W(lt) {
      var Q = new Error(Y.source + ":" + it + ":" + K + ": " + lt);
      if (
        ((Q.reason = lt),
        (Q.filename = Y.source),
        (Q.line = it),
        (Q.column = K),
        (Q.source = F),
        !Y.silent)
      )
        throw Q;
    }
    function ht(lt) {
      var Q = lt.exec(F);
      if (Q) {
        var M = Q[0];
        return (mt(M), (F = F.slice(M.length)), Q);
      }
    }
    function pt() {
      ht(r);
    }
    function Et(lt) {
      var Q;
      for (lt = lt || []; (Q = tt()); ) Q !== !1 && lt.push(Q);
      return lt;
    }
    function tt() {
      var lt = yt();
      if (!(p != F.charAt(0) || b != F.charAt(1))) {
        for (
          var Q = 2;
          v != F.charAt(Q) && (b != F.charAt(Q) || p != F.charAt(Q + 1));
        )
          ++Q;
        if (((Q += 2), v === F.charAt(Q - 1)))
          return W("End of comment missing");
        var M = F.slice(2, Q - 2);
        return (
          (K += 2),
          mt(M),
          (F = F.slice(Q)),
          (K += 2),
          lt({ type: T, comment: M })
        );
      }
    }
    function $() {
      var lt = yt(),
        Q = ht(c);
      if (Q) {
        if ((tt(), !ht(f))) return W("property missing ':'");
        var M = ht(s),
          B = lt({
            type: x,
            property: G(Q[0].replace(i, v)),
            value: M ? G(M[0].replace(i, v)) : v,
          });
        return (ht(d), B);
      }
    }
    function _t() {
      var lt = [];
      Et(lt);
      for (var Q; (Q = $()); ) Q !== !1 && (lt.push(Q), Et(lt));
      return lt;
    }
    return (pt(), _t());
  }
  function G(F) {
    return F ? F.replace(m, v) : v;
  }
  return ((vo = X), vo);
}
var pp;
function z1() {
  if (pp) return oi;
  pp = 1;
  var i =
    (oi && oi.__importDefault) ||
    function (c) {
      return c && c.__esModule ? c : { default: c };
    };
  (Object.defineProperty(oi, "__esModule", { value: !0 }), (oi.default = r));
  const u = i(E1());
  function r(c, f) {
    let s = null;
    if (!c || typeof c != "string") return s;
    const d = (0, u.default)(c),
      m = typeof f == "function";
    return (
      d.forEach((y) => {
        if (y.type !== "declaration") return;
        const { property: p, value: b } = y;
        m ? f(p, b, y) : b && ((s = s || {}), (s[p] = b));
      }),
      s
    );
  }
  return oi;
}
var fa = {},
  mp;
function T1() {
  if (mp) return fa;
  ((mp = 1),
    Object.defineProperty(fa, "__esModule", { value: !0 }),
    (fa.camelCase = void 0));
  var i = /^--[a-zA-Z0-9_-]+$/,
    u = /-([a-z])/g,
    r = /^[^-]+$/,
    c = /^-(webkit|moz|ms|o|khtml)-/,
    f = /^-(ms)-/,
    s = function (p) {
      return !p || r.test(p) || i.test(p);
    },
    d = function (p, b) {
      return b.toUpperCase();
    },
    m = function (p, b) {
      return "".concat(b, "-");
    },
    y = function (p, b) {
      return (
        b === void 0 && (b = {}),
        s(p)
          ? p
          : ((p = p.toLowerCase()),
            b.reactCompat ? (p = p.replace(f, m)) : (p = p.replace(c, m)),
            p.replace(u, d))
      );
    };
  return ((fa.camelCase = y), fa);
}
var sa, gp;
function A1() {
  if (gp) return sa;
  gp = 1;
  var i =
      (sa && sa.__importDefault) ||
      function (f) {
        return f && f.__esModule ? f : { default: f };
      },
    u = i(z1()),
    r = T1();
  function c(f, s) {
    var d = {};
    return (
      !f ||
        typeof f != "string" ||
        (0, u.default)(f, function (m, y) {
          m && y && (d[(0, r.camelCase)(m, s)] = y);
        }),
      d
    );
  }
  return ((c.default = c), (sa = c), sa);
}
var C1 = A1();
const _1 = Jp(C1),
  nm = lm("end"),
  Qo = lm("start");
function lm(i) {
  return u;
  function u(r) {
    const c = (r && r.position && r.position[i]) || {};
    if (
      typeof c.line == "number" &&
      c.line > 0 &&
      typeof c.column == "number" &&
      c.column > 0
    )
      return {
        line: c.line,
        column: c.column,
        offset:
          typeof c.offset == "number" && c.offset > -1 ? c.offset : void 0,
      };
  }
}
function O1(i) {
  const u = Qo(i),
    r = nm(i);
  if (u && r) return { start: u, end: r };
}
function pa(i) {
  return !i || typeof i != "object"
    ? ""
    : "position" in i || "type" in i
      ? yp(i.position)
      : "start" in i || "end" in i
        ? yp(i)
        : "line" in i || "column" in i
          ? Ro(i)
          : "";
}
function Ro(i) {
  return bp(i && i.line) + ":" + bp(i && i.column);
}
function yp(i) {
  return Ro(i && i.start) + "-" + Ro(i && i.end);
}
function bp(i) {
  return i && typeof i == "number" ? i : 1;
}
class pe extends Error {
  constructor(u, r, c) {
    (super(), typeof r == "string" && ((c = r), (r = void 0)));
    let f = "",
      s = {},
      d = !1;
    if (
      (r &&
        ("line" in r && "column" in r
          ? (s = { place: r })
          : "start" in r && "end" in r
            ? (s = { place: r })
            : "type" in r
              ? (s = { ancestors: [r], place: r.position })
              : (s = { ...r })),
      typeof u == "string"
        ? (f = u)
        : !s.cause && u && ((d = !0), (f = u.message), (s.cause = u)),
      !s.ruleId && !s.source && typeof c == "string")
    ) {
      const y = c.indexOf(":");
      y === -1
        ? (s.ruleId = c)
        : ((s.source = c.slice(0, y)), (s.ruleId = c.slice(y + 1)));
    }
    if (!s.place && s.ancestors && s.ancestors) {
      const y = s.ancestors[s.ancestors.length - 1];
      y && (s.place = y.position);
    }
    const m = s.place && "start" in s.place ? s.place.start : s.place;
    ((this.ancestors = s.ancestors || void 0),
      (this.cause = s.cause || void 0),
      (this.column = m ? m.column : void 0),
      (this.fatal = void 0),
      (this.file = ""),
      (this.message = f),
      (this.line = m ? m.line : void 0),
      (this.name = pa(s.place) || "1:1"),
      (this.place = s.place || void 0),
      (this.reason = this.message),
      (this.ruleId = s.ruleId || void 0),
      (this.source = s.source || void 0),
      (this.stack =
        d && s.cause && typeof s.cause.stack == "string" ? s.cause.stack : ""),
      (this.actual = void 0),
      (this.expected = void 0),
      (this.note = void 0),
      (this.url = void 0));
  }
}
pe.prototype.file = "";
pe.prototype.name = "";
pe.prototype.reason = "";
pe.prototype.message = "";
pe.prototype.stack = "";
pe.prototype.column = void 0;
pe.prototype.line = void 0;
pe.prototype.ancestors = void 0;
pe.prototype.cause = void 0;
pe.prototype.fatal = void 0;
pe.prototype.place = void 0;
pe.prototype.ruleId = void 0;
pe.prototype.source = void 0;
const Vo = {}.hasOwnProperty,
  D1 = new Map(),
  M1 = /[A-Z]/g,
  k1 = new Set(["table", "tbody", "thead", "tfoot", "tr"]),
  w1 = new Set(["td", "th"]),
  im = "https://github.com/syntax-tree/hast-util-to-jsx-runtime";
function N1(i, u) {
  if (!u || u.Fragment === void 0)
    throw new TypeError("Expected `Fragment` in options");
  const r = u.filePath || void 0;
  let c;
  if (u.development) {
    if (typeof u.jsxDEV != "function")
      throw new TypeError(
        "Expected `jsxDEV` in options when `development: true`",
      );
    c = Y1(r, u.jsxDEV);
  } else {
    if (typeof u.jsx != "function")
      throw new TypeError("Expected `jsx` in production options");
    if (typeof u.jsxs != "function")
      throw new TypeError("Expected `jsxs` in production options");
    c = q1(r, u.jsx, u.jsxs);
  }
  const f = {
      Fragment: u.Fragment,
      ancestors: [],
      components: u.components || {},
      create: c,
      elementAttributeNameCase: u.elementAttributeNameCase || "react",
      evaluater: u.createEvaluater ? u.createEvaluater() : void 0,
      filePath: r,
      ignoreInvalidStyle: u.ignoreInvalidStyle || !1,
      passKeys: u.passKeys !== !1,
      passNode: u.passNode || !1,
      schema: u.space === "svg" ? Xo : S1,
      stylePropertyNameCase: u.stylePropertyNameCase || "dom",
      tableCellAlignToStyle: u.tableCellAlignToStyle !== !1,
    },
    s = am(f, i, void 0);
  return s && typeof s != "string"
    ? s
    : f.create(i, f.Fragment, { children: s || void 0 }, void 0);
}
function am(i, u, r) {
  if (u.type === "element") return R1(i, u, r);
  if (u.type === "mdxFlowExpression" || u.type === "mdxTextExpression")
    return U1(i, u);
  if (u.type === "mdxJsxFlowElement" || u.type === "mdxJsxTextElement")
    return j1(i, u, r);
  if (u.type === "mdxjsEsm") return B1(i, u);
  if (u.type === "root") return H1(i, u, r);
  if (u.type === "text") return L1(i, u);
}
function R1(i, u, r) {
  const c = i.schema;
  let f = c;
  (u.tagName.toLowerCase() === "svg" &&
    c.space === "html" &&
    ((f = Xo), (i.schema = f)),
    i.ancestors.push(u));
  const s = rm(i, u.tagName, !1),
    d = G1(i, u);
  let m = Ko(i, u);
  return (
    k1.has(u.tagName) &&
      (m = m.filter(function (y) {
        return typeof y == "string" ? !f1(y) : !0;
      })),
    um(i, d, s, u),
    Zo(d, m),
    i.ancestors.pop(),
    (i.schema = c),
    i.create(u, s, d, r)
  );
}
function U1(i, u) {
  if (u.data && u.data.estree && i.evaluater) {
    const c = u.data.estree.body[0];
    return (c.type, i.evaluater.evaluateExpression(c.expression));
  }
  ya(i, u.position);
}
function B1(i, u) {
  if (u.data && u.data.estree && i.evaluater)
    return i.evaluater.evaluateProgram(u.data.estree);
  ya(i, u.position);
}
function j1(i, u, r) {
  const c = i.schema;
  let f = c;
  (u.name === "svg" && c.space === "html" && ((f = Xo), (i.schema = f)),
    i.ancestors.push(u));
  const s = u.name === null ? i.Fragment : rm(i, u.name, !0),
    d = X1(i, u),
    m = Ko(i, u);
  return (
    um(i, d, s, u),
    Zo(d, m),
    i.ancestors.pop(),
    (i.schema = c),
    i.create(u, s, d, r)
  );
}
function H1(i, u, r) {
  const c = {};
  return (Zo(c, Ko(i, u)), i.create(u, i.Fragment, c, r));
}
function L1(i, u) {
  return u.value;
}
function um(i, u, r, c) {
  typeof r != "string" && r !== i.Fragment && i.passNode && (u.node = c);
}
function Zo(i, u) {
  if (u.length > 0) {
    const r = u.length > 1 ? u : u[0];
    r && (i.children = r);
  }
}
function q1(i, u, r) {
  return c;
  function c(f, s, d, m) {
    const p = Array.isArray(d.children) ? r : u;
    return m ? p(s, d, m) : p(s, d);
  }
}
function Y1(i, u) {
  return r;
  function r(c, f, s, d) {
    const m = Array.isArray(s.children),
      y = Qo(c);
    return u(
      f,
      s,
      d,
      m,
      {
        columnNumber: y ? y.column - 1 : void 0,
        fileName: i,
        lineNumber: y ? y.line : void 0,
      },
      void 0,
    );
  }
}
function G1(i, u) {
  const r = {};
  let c, f;
  for (f in u.properties)
    if (f !== "children" && Vo.call(u.properties, f)) {
      const s = Q1(i, f, u.properties[f]);
      if (s) {
        const [d, m] = s;
        i.tableCellAlignToStyle &&
        d === "align" &&
        typeof m == "string" &&
        w1.has(u.tagName)
          ? (c = m)
          : (r[d] = m);
      }
    }
  if (c) {
    const s = r.style || (r.style = {});
    s[i.stylePropertyNameCase === "css" ? "text-align" : "textAlign"] = c;
  }
  return r;
}
function X1(i, u) {
  const r = {};
  for (const c of u.attributes)
    if (c.type === "mdxJsxExpressionAttribute")
      if (c.data && c.data.estree && i.evaluater) {
        const s = c.data.estree.body[0];
        s.type;
        const d = s.expression;
        d.type;
        const m = d.properties[0];
        (m.type, Object.assign(r, i.evaluater.evaluateExpression(m.argument)));
      } else ya(i, u.position);
    else {
      const f = c.name;
      let s;
      if (c.value && typeof c.value == "object")
        if (c.value.data && c.value.data.estree && i.evaluater) {
          const m = c.value.data.estree.body[0];
          (m.type, (s = i.evaluater.evaluateExpression(m.expression)));
        } else ya(i, u.position);
      else s = c.value === null ? !0 : c.value;
      r[f] = s;
    }
  return r;
}
function Ko(i, u) {
  const r = [];
  let c = -1;
  const f = i.passKeys ? new Map() : D1;
  for (; ++c < u.children.length; ) {
    const s = u.children[c];
    let d;
    if (i.passKeys) {
      const y =
        s.type === "element"
          ? s.tagName
          : s.type === "mdxJsxFlowElement" || s.type === "mdxJsxTextElement"
            ? s.name
            : void 0;
      if (y) {
        const p = f.get(y) || 0;
        ((d = y + "-" + p), f.set(y, p + 1));
      }
    }
    const m = am(i, s, d);
    m !== void 0 && r.push(m);
  }
  return r;
}
function Q1(i, u, r) {
  const c = y1(i.schema, u);
  if (!(r == null || (typeof r == "number" && Number.isNaN(r)))) {
    if (
      (Array.isArray(r) && (r = c.commaSeparated ? a1(r) : x1(r)),
      c.property === "style")
    ) {
      let f = typeof r == "object" ? r : V1(i, String(r));
      return (i.stylePropertyNameCase === "css" && (f = Z1(f)), ["style", f]);
    }
    return [
      i.elementAttributeNameCase === "react" && c.space
        ? p1[c.property] || c.property
        : c.attribute,
      r,
    ];
  }
}
function V1(i, u) {
  try {
    return _1(u, { reactCompat: !0 });
  } catch (r) {
    if (i.ignoreInvalidStyle) return {};
    const c = r,
      f = new pe("Cannot parse `style` attribute", {
        ancestors: i.ancestors,
        cause: c,
        ruleId: "style",
        source: "hast-util-to-jsx-runtime",
      });
    throw (
      (f.file = i.filePath || void 0),
      (f.url = im + "#cannot-parse-style-attribute"),
      f
    );
  }
}
function rm(i, u, r) {
  let c;
  if (!r) c = { type: "Literal", value: u };
  else if (u.includes(".")) {
    const f = u.split(".");
    let s = -1,
      d;
    for (; ++s < f.length; ) {
      const m = op(f[s])
        ? { type: "Identifier", name: f[s] }
        : { type: "Literal", value: f[s] };
      d = d
        ? {
            type: "MemberExpression",
            object: d,
            property: m,
            computed: !!(s && m.type === "Literal"),
            optional: !1,
          }
        : m;
    }
    c = d;
  } else
    c =
      op(u) && !/^[a-z]/.test(u)
        ? { type: "Identifier", name: u }
        : { type: "Literal", value: u };
  if (c.type === "Literal") {
    const f = c.value;
    return Vo.call(i.components, f) ? i.components[f] : f;
  }
  if (i.evaluater) return i.evaluater.evaluateExpression(c);
  ya(i);
}
function ya(i, u) {
  const r = new pe("Cannot handle MDX estrees without `createEvaluater`", {
    ancestors: i.ancestors,
    place: u,
    ruleId: "mdx-estree",
    source: "hast-util-to-jsx-runtime",
  });
  throw (
    (r.file = i.filePath || void 0),
    (r.url = im + "#cannot-handle-mdx-estrees-without-createevaluater"),
    r
  );
}
function Z1(i) {
  const u = {};
  let r;
  for (r in i) Vo.call(i, r) && (u[K1(r)] = i[r]);
  return u;
}
function K1(i) {
  let u = i.replace(M1, J1);
  return (u.slice(0, 3) === "ms-" && (u = "-" + u), u);
}
function J1(i) {
  return "-" + i.toLowerCase();
}
const So = {
    action: ["form"],
    cite: ["blockquote", "del", "ins", "q"],
    data: ["object"],
    formAction: ["button", "input"],
    href: ["a", "area", "base", "link"],
    icon: ["menuitem"],
    itemId: null,
    manifest: ["html"],
    ping: ["a", "area"],
    poster: ["video"],
    src: [
      "audio",
      "embed",
      "iframe",
      "img",
      "input",
      "script",
      "source",
      "track",
      "video",
    ],
  },
  F1 = {};
function I1(i, u) {
  const r = F1,
    c = typeof r.includeImageAlt == "boolean" ? r.includeImageAlt : !0,
    f = typeof r.includeHtml == "boolean" ? r.includeHtml : !0;
  return cm(i, c, f);
}
function cm(i, u, r) {
  if (W1(i)) {
    if ("value" in i) return i.type === "html" && !r ? "" : i.value;
    if (u && "alt" in i && i.alt) return i.alt;
    if ("children" in i) return vp(i.children, u, r);
  }
  return Array.isArray(i) ? vp(i, u, r) : "";
}
function vp(i, u, r) {
  const c = [];
  let f = -1;
  for (; ++f < i.length; ) c[f] = cm(i[f], u, r);
  return c.join("");
}
function W1(i) {
  return !!(i && typeof i == "object");
}
const Sp = document.createElement("i");
function Jo(i) {
  const u = "&" + i + ";";
  Sp.innerHTML = u;
  const r = Sp.textContent;
  return (r.charCodeAt(r.length - 1) === 59 && i !== "semi") || r === u
    ? !1
    : r;
}
function cn(i, u, r, c) {
  const f = i.length;
  let s = 0,
    d;
  if (
    (u < 0 ? (u = -u > f ? 0 : f + u) : (u = u > f ? f : u),
    (r = r > 0 ? r : 0),
    c.length < 1e4)
  )
    ((d = Array.from(c)), d.unshift(u, r), i.splice(...d));
  else
    for (r && i.splice(u, r); s < c.length; )
      ((d = c.slice(s, s + 1e4)),
        d.unshift(u, 0),
        i.splice(...d),
        (s += 1e4),
        (u += 1e4));
}
function Ie(i, u) {
  return i.length > 0 ? (cn(i, i.length, 0, u), i) : u;
}
const xp = {}.hasOwnProperty;
function $1(i) {
  const u = {};
  let r = -1;
  for (; ++r < i.length; ) P1(u, i[r]);
  return u;
}
function P1(i, u) {
  let r;
  for (r in u) {
    const f = (xp.call(i, r) ? i[r] : void 0) || (i[r] = {}),
      s = u[r];
    let d;
    if (s)
      for (d in s) {
        xp.call(f, d) || (f[d] = []);
        const m = s[d];
        t0(f[d], Array.isArray(m) ? m : m ? [m] : []);
      }
  }
}
function t0(i, u) {
  let r = -1;
  const c = [];
  for (; ++r < u.length; ) (u[r].add === "after" ? i : c).push(u[r]);
  cn(i, 0, 0, c);
}
function om(i, u) {
  const r = Number.parseInt(i, u);
  return r < 9 ||
    r === 11 ||
    (r > 13 && r < 32) ||
    (r > 126 && r < 160) ||
    (r > 55295 && r < 57344) ||
    (r > 64975 && r < 65008) ||
    (r & 65535) === 65535 ||
    (r & 65535) === 65534 ||
    r > 1114111
    ? "�"
    : String.fromCodePoint(r);
}
function hi(i) {
  return i
    .replace(/[\t\n\r ]+/g, " ")
    .replace(/^ | $/g, "")
    .toLowerCase()
    .toUpperCase();
}
const rn = el(/[A-Za-z]/),
  Le = el(/[\dA-Za-z]/),
  e0 = el(/[#-'*+\--9=?A-Z^-~]/);
function Uo(i) {
  return i !== null && (i < 32 || i === 127);
}
const Bo = el(/\d/),
  n0 = el(/[\dA-Fa-f]/),
  l0 = el(/[!-/:-@[-`{-~]/);
function st(i) {
  return i !== null && i < -2;
}
function Oe(i) {
  return i !== null && (i < 0 || i === 32);
}
function Ut(i) {
  return i === -2 || i === -1 || i === 32;
}
const i0 = el(new RegExp("\\p{P}|\\p{S}", "u")),
  a0 = el(/\s/);
function el(i) {
  return u;
  function u(r) {
    return r !== null && r > -1 && i.test(String.fromCharCode(r));
  }
}
function pi(i) {
  const u = [];
  let r = -1,
    c = 0,
    f = 0;
  for (; ++r < i.length; ) {
    const s = i.charCodeAt(r);
    let d = "";
    if (s === 37 && Le(i.charCodeAt(r + 1)) && Le(i.charCodeAt(r + 2))) f = 2;
    else if (s < 128)
      /[!#$&-;=?-Z_a-z~]/.test(String.fromCharCode(s)) ||
        (d = String.fromCharCode(s));
    else if (s > 55295 && s < 57344) {
      const m = i.charCodeAt(r + 1);
      s < 56320 && m > 56319 && m < 57344
        ? ((d = String.fromCharCode(s, m)), (f = 1))
        : (d = "�");
    } else d = String.fromCharCode(s);
    (d &&
      (u.push(i.slice(c, r), encodeURIComponent(d)), (c = r + f + 1), (d = "")),
      f && ((r += f), (f = 0)));
  }
  return u.join("") + i.slice(c);
}
function Vt(i, u, r, c) {
  const f = c ? c - 1 : Number.POSITIVE_INFINITY;
  let s = 0;
  return d;
  function d(y) {
    return Ut(y) ? (i.enter(r), m(y)) : u(y);
  }
  function m(y) {
    return Ut(y) && s++ < f ? (i.consume(y), m) : (i.exit(r), u(y));
  }
}
const u0 = { tokenize: r0 };
function r0(i) {
  const u = i.attempt(this.parser.constructs.contentInitial, c, f);
  let r;
  return u;
  function c(m) {
    if (m === null) {
      i.consume(m);
      return;
    }
    return (
      i.enter("lineEnding"),
      i.consume(m),
      i.exit("lineEnding"),
      Vt(i, u, "linePrefix")
    );
  }
  function f(m) {
    return (i.enter("paragraph"), s(m));
  }
  function s(m) {
    const y = i.enter("chunkText", { contentType: "text", previous: r });
    return (r && (r.next = y), (r = y), d(m));
  }
  function d(m) {
    if (m === null) {
      (i.exit("chunkText"), i.exit("paragraph"), i.consume(m));
      return;
    }
    return st(m) ? (i.consume(m), i.exit("chunkText"), s) : (i.consume(m), d);
  }
}
const c0 = { tokenize: o0 },
  Ep = { tokenize: f0 };
function o0(i) {
  const u = this,
    r = [];
  let c = 0,
    f,
    s,
    d;
  return m;
  function m(K) {
    if (c < r.length) {
      const mt = r[c];
      return (
        (u.containerState = mt[1]),
        i.attempt(mt[0].continuation, y, p)(K)
      );
    }
    return p(K);
  }
  function y(K) {
    if ((c++, u.containerState._closeFlow)) {
      ((u.containerState._closeFlow = void 0), f && it());
      const mt = u.events.length;
      let yt = mt,
        H;
      for (; yt--; )
        if (
          u.events[yt][0] === "exit" &&
          u.events[yt][1].type === "chunkFlow"
        ) {
          H = u.events[yt][1].end;
          break;
        }
      Y(c);
      let W = mt;
      for (; W < u.events.length; ) ((u.events[W][1].end = { ...H }), W++);
      return (
        cn(u.events, yt + 1, 0, u.events.slice(mt)),
        (u.events.length = W),
        p(K)
      );
    }
    return m(K);
  }
  function p(K) {
    if (c === r.length) {
      if (!f) return T(K);
      if (f.currentConstruct && f.currentConstruct.concrete) return X(K);
      u.interrupt = !!(f.currentConstruct && !f._gfmTableDynamicInterruptHack);
    }
    return ((u.containerState = {}), i.check(Ep, b, v)(K));
  }
  function b(K) {
    return (f && it(), Y(c), T(K));
  }
  function v(K) {
    return (
      (u.parser.lazy[u.now().line] = c !== r.length),
      (d = u.now().offset),
      X(K)
    );
  }
  function T(K) {
    return ((u.containerState = {}), i.attempt(Ep, x, X)(K));
  }
  function x(K) {
    return (c++, r.push([u.currentConstruct, u.containerState]), T(K));
  }
  function X(K) {
    if (K === null) {
      (f && it(), Y(0), i.consume(K));
      return;
    }
    return (
      (f = f || u.parser.flow(u.now())),
      i.enter("chunkFlow", { _tokenizer: f, contentType: "flow", previous: s }),
      G(K)
    );
  }
  function G(K) {
    if (K === null) {
      (F(i.exit("chunkFlow"), !0), Y(0), i.consume(K));
      return;
    }
    return st(K)
      ? (i.consume(K),
        F(i.exit("chunkFlow")),
        (c = 0),
        (u.interrupt = void 0),
        m)
      : (i.consume(K), G);
  }
  function F(K, mt) {
    const yt = u.sliceStream(K);
    if (
      (mt && yt.push(null),
      (K.previous = s),
      s && (s.next = K),
      (s = K),
      f.defineSkip(K.start),
      f.write(yt),
      u.parser.lazy[K.start.line])
    ) {
      let H = f.events.length;
      for (; H--; )
        if (
          f.events[H][1].start.offset < d &&
          (!f.events[H][1].end || f.events[H][1].end.offset > d)
        )
          return;
      const W = u.events.length;
      let ht = W,
        pt,
        Et;
      for (; ht--; )
        if (
          u.events[ht][0] === "exit" &&
          u.events[ht][1].type === "chunkFlow"
        ) {
          if (pt) {
            Et = u.events[ht][1].end;
            break;
          }
          pt = !0;
        }
      for (Y(c), H = W; H < u.events.length; )
        ((u.events[H][1].end = { ...Et }), H++);
      (cn(u.events, ht + 1, 0, u.events.slice(W)), (u.events.length = H));
    }
  }
  function Y(K) {
    let mt = r.length;
    for (; mt-- > K; ) {
      const yt = r[mt];
      ((u.containerState = yt[1]), yt[0].exit.call(u, i));
    }
    r.length = K;
  }
  function it() {
    (f.write([null]),
      (s = void 0),
      (f = void 0),
      (u.containerState._closeFlow = void 0));
  }
}
function f0(i, u, r) {
  return Vt(
    i,
    i.attempt(this.parser.constructs.document, u, r),
    "linePrefix",
    this.parser.constructs.disable.null.includes("codeIndented") ? void 0 : 4,
  );
}
function zp(i) {
  if (i === null || Oe(i) || a0(i)) return 1;
  if (i0(i)) return 2;
}
function Fo(i, u, r) {
  const c = [];
  let f = -1;
  for (; ++f < i.length; ) {
    const s = i[f].resolveAll;
    s && !c.includes(s) && ((u = s(u, r)), c.push(s));
  }
  return u;
}
const jo = { name: "attention", resolveAll: s0, tokenize: h0 };
function s0(i, u) {
  let r = -1,
    c,
    f,
    s,
    d,
    m,
    y,
    p,
    b;
  for (; ++r < i.length; )
    if (
      i[r][0] === "enter" &&
      i[r][1].type === "attentionSequence" &&
      i[r][1]._close
    ) {
      for (c = r; c--; )
        if (
          i[c][0] === "exit" &&
          i[c][1].type === "attentionSequence" &&
          i[c][1]._open &&
          u.sliceSerialize(i[c][1]).charCodeAt(0) ===
            u.sliceSerialize(i[r][1]).charCodeAt(0)
        ) {
          if (
            (i[c][1]._close || i[r][1]._open) &&
            (i[r][1].end.offset - i[r][1].start.offset) % 3 &&
            !(
              (i[c][1].end.offset -
                i[c][1].start.offset +
                i[r][1].end.offset -
                i[r][1].start.offset) %
              3
            )
          )
            continue;
          y =
            i[c][1].end.offset - i[c][1].start.offset > 1 &&
            i[r][1].end.offset - i[r][1].start.offset > 1
              ? 2
              : 1;
          const v = { ...i[c][1].end },
            T = { ...i[r][1].start };
          (Tp(v, -y),
            Tp(T, y),
            (d = {
              type: y > 1 ? "strongSequence" : "emphasisSequence",
              start: v,
              end: { ...i[c][1].end },
            }),
            (m = {
              type: y > 1 ? "strongSequence" : "emphasisSequence",
              start: { ...i[r][1].start },
              end: T,
            }),
            (s = {
              type: y > 1 ? "strongText" : "emphasisText",
              start: { ...i[c][1].end },
              end: { ...i[r][1].start },
            }),
            (f = {
              type: y > 1 ? "strong" : "emphasis",
              start: { ...d.start },
              end: { ...m.end },
            }),
            (i[c][1].end = { ...d.start }),
            (i[r][1].start = { ...m.end }),
            (p = []),
            i[c][1].end.offset - i[c][1].start.offset &&
              (p = Ie(p, [
                ["enter", i[c][1], u],
                ["exit", i[c][1], u],
              ])),
            (p = Ie(p, [
              ["enter", f, u],
              ["enter", d, u],
              ["exit", d, u],
              ["enter", s, u],
            ])),
            (p = Ie(
              p,
              Fo(u.parser.constructs.insideSpan.null, i.slice(c + 1, r), u),
            )),
            (p = Ie(p, [
              ["exit", s, u],
              ["enter", m, u],
              ["exit", m, u],
              ["exit", f, u],
            ])),
            i[r][1].end.offset - i[r][1].start.offset
              ? ((b = 2),
                (p = Ie(p, [
                  ["enter", i[r][1], u],
                  ["exit", i[r][1], u],
                ])))
              : (b = 0),
            cn(i, c - 1, r - c + 3, p),
            (r = c + p.length - b - 2));
          break;
        }
    }
  for (r = -1; ++r < i.length; )
    i[r][1].type === "attentionSequence" && (i[r][1].type = "data");
  return i;
}
function h0(i, u) {
  const r = this.parser.constructs.attentionMarkers.null,
    c = this.previous,
    f = zp(c);
  let s;
  return d;
  function d(y) {
    return ((s = y), i.enter("attentionSequence"), m(y));
  }
  function m(y) {
    if (y === s) return (i.consume(y), m);
    const p = i.exit("attentionSequence"),
      b = zp(y),
      v = !b || (b === 2 && f) || r.includes(y),
      T = !f || (f === 2 && b) || r.includes(c);
    return (
      (p._open = !!(s === 42 ? v : v && (f || !T))),
      (p._close = !!(s === 42 ? T : T && (b || !v))),
      u(y)
    );
  }
}
function Tp(i, u) {
  ((i.column += u), (i.offset += u), (i._bufferIndex += u));
}
const d0 = { name: "autolink", tokenize: p0 };
function p0(i, u, r) {
  let c = 0;
  return f;
  function f(x) {
    return (
      i.enter("autolink"),
      i.enter("autolinkMarker"),
      i.consume(x),
      i.exit("autolinkMarker"),
      i.enter("autolinkProtocol"),
      s
    );
  }
  function s(x) {
    return rn(x) ? (i.consume(x), d) : x === 64 ? r(x) : p(x);
  }
  function d(x) {
    return x === 43 || x === 45 || x === 46 || Le(x) ? ((c = 1), m(x)) : p(x);
  }
  function m(x) {
    return x === 58
      ? (i.consume(x), (c = 0), y)
      : (x === 43 || x === 45 || x === 46 || Le(x)) && c++ < 32
        ? (i.consume(x), m)
        : ((c = 0), p(x));
  }
  function y(x) {
    return x === 62
      ? (i.exit("autolinkProtocol"),
        i.enter("autolinkMarker"),
        i.consume(x),
        i.exit("autolinkMarker"),
        i.exit("autolink"),
        u)
      : x === null || x === 32 || x === 60 || Uo(x)
        ? r(x)
        : (i.consume(x), y);
  }
  function p(x) {
    return x === 64 ? (i.consume(x), b) : e0(x) ? (i.consume(x), p) : r(x);
  }
  function b(x) {
    return Le(x) ? v(x) : r(x);
  }
  function v(x) {
    return x === 46
      ? (i.consume(x), (c = 0), b)
      : x === 62
        ? ((i.exit("autolinkProtocol").type = "autolinkEmail"),
          i.enter("autolinkMarker"),
          i.consume(x),
          i.exit("autolinkMarker"),
          i.exit("autolink"),
          u)
        : T(x);
  }
  function T(x) {
    if ((x === 45 || Le(x)) && c++ < 63) {
      const X = x === 45 ? T : v;
      return (i.consume(x), X);
    }
    return r(x);
  }
}
const Zu = { partial: !0, tokenize: m0 };
function m0(i, u, r) {
  return c;
  function c(s) {
    return Ut(s) ? Vt(i, f, "linePrefix")(s) : f(s);
  }
  function f(s) {
    return s === null || st(s) ? u(s) : r(s);
  }
}
const fm = {
  continuation: { tokenize: y0 },
  exit: b0,
  name: "blockQuote",
  tokenize: g0,
};
function g0(i, u, r) {
  const c = this;
  return f;
  function f(d) {
    if (d === 62) {
      const m = c.containerState;
      return (
        m.open || (i.enter("blockQuote", { _container: !0 }), (m.open = !0)),
        i.enter("blockQuotePrefix"),
        i.enter("blockQuoteMarker"),
        i.consume(d),
        i.exit("blockQuoteMarker"),
        s
      );
    }
    return r(d);
  }
  function s(d) {
    return Ut(d)
      ? (i.enter("blockQuotePrefixWhitespace"),
        i.consume(d),
        i.exit("blockQuotePrefixWhitespace"),
        i.exit("blockQuotePrefix"),
        u)
      : (i.exit("blockQuotePrefix"), u(d));
  }
}
function y0(i, u, r) {
  const c = this;
  return f;
  function f(d) {
    return Ut(d)
      ? Vt(
          i,
          s,
          "linePrefix",
          c.parser.constructs.disable.null.includes("codeIndented")
            ? void 0
            : 4,
        )(d)
      : s(d);
  }
  function s(d) {
    return i.attempt(fm, u, r)(d);
  }
}
function b0(i) {
  i.exit("blockQuote");
}
const sm = { name: "characterEscape", tokenize: v0 };
function v0(i, u, r) {
  return c;
  function c(s) {
    return (
      i.enter("characterEscape"),
      i.enter("escapeMarker"),
      i.consume(s),
      i.exit("escapeMarker"),
      f
    );
  }
  function f(s) {
    return l0(s)
      ? (i.enter("characterEscapeValue"),
        i.consume(s),
        i.exit("characterEscapeValue"),
        i.exit("characterEscape"),
        u)
      : r(s);
  }
}
const hm = { name: "characterReference", tokenize: S0 };
function S0(i, u, r) {
  const c = this;
  let f = 0,
    s,
    d;
  return m;
  function m(v) {
    return (
      i.enter("characterReference"),
      i.enter("characterReferenceMarker"),
      i.consume(v),
      i.exit("characterReferenceMarker"),
      y
    );
  }
  function y(v) {
    return v === 35
      ? (i.enter("characterReferenceMarkerNumeric"),
        i.consume(v),
        i.exit("characterReferenceMarkerNumeric"),
        p)
      : (i.enter("characterReferenceValue"), (s = 31), (d = Le), b(v));
  }
  function p(v) {
    return v === 88 || v === 120
      ? (i.enter("characterReferenceMarkerHexadecimal"),
        i.consume(v),
        i.exit("characterReferenceMarkerHexadecimal"),
        i.enter("characterReferenceValue"),
        (s = 6),
        (d = n0),
        b)
      : (i.enter("characterReferenceValue"), (s = 7), (d = Bo), b(v));
  }
  function b(v) {
    if (v === 59 && f) {
      const T = i.exit("characterReferenceValue");
      return d === Le && !Jo(c.sliceSerialize(T))
        ? r(v)
        : (i.enter("characterReferenceMarker"),
          i.consume(v),
          i.exit("characterReferenceMarker"),
          i.exit("characterReference"),
          u);
    }
    return d(v) && f++ < s ? (i.consume(v), b) : r(v);
  }
}
const Ap = { partial: !0, tokenize: E0 },
  Cp = { concrete: !0, name: "codeFenced", tokenize: x0 };
function x0(i, u, r) {
  const c = this,
    f = { partial: !0, tokenize: yt };
  let s = 0,
    d = 0,
    m;
  return y;
  function y(H) {
    return p(H);
  }
  function p(H) {
    const W = c.events[c.events.length - 1];
    return (
      (s =
        W && W[1].type === "linePrefix"
          ? W[2].sliceSerialize(W[1], !0).length
          : 0),
      (m = H),
      i.enter("codeFenced"),
      i.enter("codeFencedFence"),
      i.enter("codeFencedFenceSequence"),
      b(H)
    );
  }
  function b(H) {
    return H === m
      ? (d++, i.consume(H), b)
      : d < 3
        ? r(H)
        : (i.exit("codeFencedFenceSequence"),
          Ut(H) ? Vt(i, v, "whitespace")(H) : v(H));
  }
  function v(H) {
    return H === null || st(H)
      ? (i.exit("codeFencedFence"), c.interrupt ? u(H) : i.check(Ap, G, mt)(H))
      : (i.enter("codeFencedFenceInfo"),
        i.enter("chunkString", { contentType: "string" }),
        T(H));
  }
  function T(H) {
    return H === null || st(H)
      ? (i.exit("chunkString"), i.exit("codeFencedFenceInfo"), v(H))
      : Ut(H)
        ? (i.exit("chunkString"),
          i.exit("codeFencedFenceInfo"),
          Vt(i, x, "whitespace")(H))
        : H === 96 && H === m
          ? r(H)
          : (i.consume(H), T);
  }
  function x(H) {
    return H === null || st(H)
      ? v(H)
      : (i.enter("codeFencedFenceMeta"),
        i.enter("chunkString", { contentType: "string" }),
        X(H));
  }
  function X(H) {
    return H === null || st(H)
      ? (i.exit("chunkString"), i.exit("codeFencedFenceMeta"), v(H))
      : H === 96 && H === m
        ? r(H)
        : (i.consume(H), X);
  }
  function G(H) {
    return i.attempt(f, mt, F)(H);
  }
  function F(H) {
    return (i.enter("lineEnding"), i.consume(H), i.exit("lineEnding"), Y);
  }
  function Y(H) {
    return s > 0 && Ut(H) ? Vt(i, it, "linePrefix", s + 1)(H) : it(H);
  }
  function it(H) {
    return H === null || st(H)
      ? i.check(Ap, G, mt)(H)
      : (i.enter("codeFlowValue"), K(H));
  }
  function K(H) {
    return H === null || st(H)
      ? (i.exit("codeFlowValue"), it(H))
      : (i.consume(H), K);
  }
  function mt(H) {
    return (i.exit("codeFenced"), u(H));
  }
  function yt(H, W, ht) {
    let pt = 0;
    return Et;
    function Et(Q) {
      return (H.enter("lineEnding"), H.consume(Q), H.exit("lineEnding"), tt);
    }
    function tt(Q) {
      return (
        H.enter("codeFencedFence"),
        Ut(Q)
          ? Vt(
              H,
              $,
              "linePrefix",
              c.parser.constructs.disable.null.includes("codeIndented")
                ? void 0
                : 4,
            )(Q)
          : $(Q)
      );
    }
    function $(Q) {
      return Q === m ? (H.enter("codeFencedFenceSequence"), _t(Q)) : ht(Q);
    }
    function _t(Q) {
      return Q === m
        ? (pt++, H.consume(Q), _t)
        : pt >= d
          ? (H.exit("codeFencedFenceSequence"),
            Ut(Q) ? Vt(H, lt, "whitespace")(Q) : lt(Q))
          : ht(Q);
    }
    function lt(Q) {
      return Q === null || st(Q) ? (H.exit("codeFencedFence"), W(Q)) : ht(Q);
    }
  }
}
function E0(i, u, r) {
  const c = this;
  return f;
  function f(d) {
    return d === null
      ? r(d)
      : (i.enter("lineEnding"), i.consume(d), i.exit("lineEnding"), s);
  }
  function s(d) {
    return c.parser.lazy[c.now().line] ? r(d) : u(d);
  }
}
const xo = { name: "codeIndented", tokenize: T0 },
  z0 = { partial: !0, tokenize: A0 };
function T0(i, u, r) {
  const c = this;
  return f;
  function f(p) {
    return (i.enter("codeIndented"), Vt(i, s, "linePrefix", 5)(p));
  }
  function s(p) {
    const b = c.events[c.events.length - 1];
    return b &&
      b[1].type === "linePrefix" &&
      b[2].sliceSerialize(b[1], !0).length >= 4
      ? d(p)
      : r(p);
  }
  function d(p) {
    return p === null
      ? y(p)
      : st(p)
        ? i.attempt(z0, d, y)(p)
        : (i.enter("codeFlowValue"), m(p));
  }
  function m(p) {
    return p === null || st(p)
      ? (i.exit("codeFlowValue"), d(p))
      : (i.consume(p), m);
  }
  function y(p) {
    return (i.exit("codeIndented"), u(p));
  }
}
function A0(i, u, r) {
  const c = this;
  return f;
  function f(d) {
    return c.parser.lazy[c.now().line]
      ? r(d)
      : st(d)
        ? (i.enter("lineEnding"), i.consume(d), i.exit("lineEnding"), f)
        : Vt(i, s, "linePrefix", 5)(d);
  }
  function s(d) {
    const m = c.events[c.events.length - 1];
    return m &&
      m[1].type === "linePrefix" &&
      m[2].sliceSerialize(m[1], !0).length >= 4
      ? u(d)
      : st(d)
        ? f(d)
        : r(d);
  }
}
const C0 = { name: "codeText", previous: O0, resolve: _0, tokenize: D0 };
function _0(i) {
  let u = i.length - 4,
    r = 3,
    c,
    f;
  if (
    (i[r][1].type === "lineEnding" || i[r][1].type === "space") &&
    (i[u][1].type === "lineEnding" || i[u][1].type === "space")
  ) {
    for (c = r; ++c < u; )
      if (i[c][1].type === "codeTextData") {
        ((i[r][1].type = "codeTextPadding"),
          (i[u][1].type = "codeTextPadding"),
          (r += 2),
          (u -= 2));
        break;
      }
  }
  for (c = r - 1, u++; ++c <= u; )
    f === void 0
      ? c !== u && i[c][1].type !== "lineEnding" && (f = c)
      : (c === u || i[c][1].type === "lineEnding") &&
        ((i[f][1].type = "codeTextData"),
        c !== f + 2 &&
          ((i[f][1].end = i[c - 1][1].end),
          i.splice(f + 2, c - f - 2),
          (u -= c - f - 2),
          (c = f + 2)),
        (f = void 0));
  return i;
}
function O0(i) {
  return (
    i !== 96 ||
    this.events[this.events.length - 1][1].type === "characterEscape"
  );
}
function D0(i, u, r) {
  let c = 0,
    f,
    s;
  return d;
  function d(v) {
    return (i.enter("codeText"), i.enter("codeTextSequence"), m(v));
  }
  function m(v) {
    return v === 96
      ? (i.consume(v), c++, m)
      : (i.exit("codeTextSequence"), y(v));
  }
  function y(v) {
    return v === null
      ? r(v)
      : v === 32
        ? (i.enter("space"), i.consume(v), i.exit("space"), y)
        : v === 96
          ? ((s = i.enter("codeTextSequence")), (f = 0), b(v))
          : st(v)
            ? (i.enter("lineEnding"), i.consume(v), i.exit("lineEnding"), y)
            : (i.enter("codeTextData"), p(v));
  }
  function p(v) {
    return v === null || v === 32 || v === 96 || st(v)
      ? (i.exit("codeTextData"), y(v))
      : (i.consume(v), p);
  }
  function b(v) {
    return v === 96
      ? (i.consume(v), f++, b)
      : f === c
        ? (i.exit("codeTextSequence"), i.exit("codeText"), u(v))
        : ((s.type = "codeTextData"), p(v));
  }
}
class M0 {
  constructor(u) {
    ((this.left = u ? [...u] : []), (this.right = []));
  }
  get(u) {
    if (u < 0 || u >= this.left.length + this.right.length)
      throw new RangeError(
        "Cannot access index `" +
          u +
          "` in a splice buffer of size `" +
          (this.left.length + this.right.length) +
          "`",
      );
    return u < this.left.length
      ? this.left[u]
      : this.right[this.right.length - u + this.left.length - 1];
  }
  get length() {
    return this.left.length + this.right.length;
  }
  shift() {
    return (this.setCursor(0), this.right.pop());
  }
  slice(u, r) {
    const c = r ?? Number.POSITIVE_INFINITY;
    return c < this.left.length
      ? this.left.slice(u, c)
      : u > this.left.length
        ? this.right
            .slice(
              this.right.length - c + this.left.length,
              this.right.length - u + this.left.length,
            )
            .reverse()
        : this.left
            .slice(u)
            .concat(
              this.right
                .slice(this.right.length - c + this.left.length)
                .reverse(),
            );
  }
  splice(u, r, c) {
    const f = r || 0;
    this.setCursor(Math.trunc(u));
    const s = this.right.splice(
      this.right.length - f,
      Number.POSITIVE_INFINITY,
    );
    return (c && ha(this.left, c), s.reverse());
  }
  pop() {
    return (this.setCursor(Number.POSITIVE_INFINITY), this.left.pop());
  }
  push(u) {
    (this.setCursor(Number.POSITIVE_INFINITY), this.left.push(u));
  }
  pushMany(u) {
    (this.setCursor(Number.POSITIVE_INFINITY), ha(this.left, u));
  }
  unshift(u) {
    (this.setCursor(0), this.right.push(u));
  }
  unshiftMany(u) {
    (this.setCursor(0), ha(this.right, u.reverse()));
  }
  setCursor(u) {
    if (
      !(
        u === this.left.length ||
        (u > this.left.length && this.right.length === 0) ||
        (u < 0 && this.left.length === 0)
      )
    )
      if (u < this.left.length) {
        const r = this.left.splice(u, Number.POSITIVE_INFINITY);
        ha(this.right, r.reverse());
      } else {
        const r = this.right.splice(
          this.left.length + this.right.length - u,
          Number.POSITIVE_INFINITY,
        );
        ha(this.left, r.reverse());
      }
  }
}
function ha(i, u) {
  let r = 0;
  if (u.length < 1e4) i.push(...u);
  else for (; r < u.length; ) (i.push(...u.slice(r, r + 1e4)), (r += 1e4));
}
function dm(i) {
  const u = {};
  let r = -1,
    c,
    f,
    s,
    d,
    m,
    y,
    p;
  const b = new M0(i);
  for (; ++r < b.length; ) {
    for (; r in u; ) r = u[r];
    if (
      ((c = b.get(r)),
      r &&
        c[1].type === "chunkFlow" &&
        b.get(r - 1)[1].type === "listItemPrefix" &&
        ((y = c[1]._tokenizer.events),
        (s = 0),
        s < y.length && y[s][1].type === "lineEndingBlank" && (s += 2),
        s < y.length && y[s][1].type === "content"))
    )
      for (; ++s < y.length && y[s][1].type !== "content"; )
        y[s][1].type === "chunkText" &&
          ((y[s][1]._isInFirstContentOfListItem = !0), s++);
    if (c[0] === "enter")
      c[1].contentType && (Object.assign(u, k0(b, r)), (r = u[r]), (p = !0));
    else if (c[1]._container) {
      for (s = r, f = void 0; s--; )
        if (
          ((d = b.get(s)),
          d[1].type === "lineEnding" || d[1].type === "lineEndingBlank")
        )
          d[0] === "enter" &&
            (f && (b.get(f)[1].type = "lineEndingBlank"),
            (d[1].type = "lineEnding"),
            (f = s));
        else if (
          !(d[1].type === "linePrefix" || d[1].type === "listItemIndent")
        )
          break;
      f &&
        ((c[1].end = { ...b.get(f)[1].start }),
        (m = b.slice(f, r)),
        m.unshift(c),
        b.splice(f, r - f + 1, m));
    }
  }
  return (cn(i, 0, Number.POSITIVE_INFINITY, b.slice(0)), !p);
}
function k0(i, u) {
  const r = i.get(u)[1],
    c = i.get(u)[2];
  let f = u - 1;
  const s = [];
  let d = r._tokenizer;
  d ||
    ((d = c.parser[r.contentType](r.start)),
    r._contentTypeTextTrailing && (d._contentTypeTextTrailing = !0));
  const m = d.events,
    y = [],
    p = {};
  let b,
    v,
    T = -1,
    x = r,
    X = 0,
    G = 0;
  const F = [G];
  for (; x; ) {
    for (; i.get(++f)[1] !== x; );
    (s.push(f),
      x._tokenizer ||
        ((b = c.sliceStream(x)),
        x.next || b.push(null),
        v && d.defineSkip(x.start),
        x._isInFirstContentOfListItem &&
          (d._gfmTasklistFirstContentOfListItem = !0),
        d.write(b),
        x._isInFirstContentOfListItem &&
          (d._gfmTasklistFirstContentOfListItem = void 0)),
      (v = x),
      (x = x.next));
  }
  for (x = r; ++T < m.length; )
    m[T][0] === "exit" &&
      m[T - 1][0] === "enter" &&
      m[T][1].type === m[T - 1][1].type &&
      m[T][1].start.line !== m[T][1].end.line &&
      ((G = T + 1),
      F.push(G),
      (x._tokenizer = void 0),
      (x.previous = void 0),
      (x = x.next));
  for (
    d.events = [],
      x ? ((x._tokenizer = void 0), (x.previous = void 0)) : F.pop(),
      T = F.length;
    T--;
  ) {
    const Y = m.slice(F[T], F[T + 1]),
      it = s.pop();
    (y.push([it, it + Y.length - 1]), i.splice(it, 2, Y));
  }
  for (y.reverse(), T = -1; ++T < y.length; )
    ((p[X + y[T][0]] = X + y[T][1]), (X += y[T][1] - y[T][0] - 1));
  return p;
}
const w0 = { resolve: R0, tokenize: U0 },
  N0 = { partial: !0, tokenize: B0 };
function R0(i) {
  return (dm(i), i);
}
function U0(i, u) {
  let r;
  return c;
  function c(m) {
    return (
      i.enter("content"),
      (r = i.enter("chunkContent", { contentType: "content" })),
      f(m)
    );
  }
  function f(m) {
    return m === null ? s(m) : st(m) ? i.check(N0, d, s)(m) : (i.consume(m), f);
  }
  function s(m) {
    return (i.exit("chunkContent"), i.exit("content"), u(m));
  }
  function d(m) {
    return (
      i.consume(m),
      i.exit("chunkContent"),
      (r.next = i.enter("chunkContent", {
        contentType: "content",
        previous: r,
      })),
      (r = r.next),
      f
    );
  }
}
function B0(i, u, r) {
  const c = this;
  return f;
  function f(d) {
    return (
      i.exit("chunkContent"),
      i.enter("lineEnding"),
      i.consume(d),
      i.exit("lineEnding"),
      Vt(i, s, "linePrefix")
    );
  }
  function s(d) {
    if (d === null || st(d)) return r(d);
    const m = c.events[c.events.length - 1];
    return !c.parser.constructs.disable.null.includes("codeIndented") &&
      m &&
      m[1].type === "linePrefix" &&
      m[2].sliceSerialize(m[1], !0).length >= 4
      ? u(d)
      : i.interrupt(c.parser.constructs.flow, r, u)(d);
  }
}
function pm(i, u, r, c, f, s, d, m, y) {
  const p = y || Number.POSITIVE_INFINITY;
  let b = 0;
  return v;
  function v(Y) {
    return Y === 60
      ? (i.enter(c), i.enter(f), i.enter(s), i.consume(Y), i.exit(s), T)
      : Y === null || Y === 32 || Y === 41 || Uo(Y)
        ? r(Y)
        : (i.enter(c),
          i.enter(d),
          i.enter(m),
          i.enter("chunkString", { contentType: "string" }),
          G(Y));
  }
  function T(Y) {
    return Y === 62
      ? (i.enter(s), i.consume(Y), i.exit(s), i.exit(f), i.exit(c), u)
      : (i.enter(m), i.enter("chunkString", { contentType: "string" }), x(Y));
  }
  function x(Y) {
    return Y === 62
      ? (i.exit("chunkString"), i.exit(m), T(Y))
      : Y === null || Y === 60 || st(Y)
        ? r(Y)
        : (i.consume(Y), Y === 92 ? X : x);
  }
  function X(Y) {
    return Y === 60 || Y === 62 || Y === 92 ? (i.consume(Y), x) : x(Y);
  }
  function G(Y) {
    return !b && (Y === null || Y === 41 || Oe(Y))
      ? (i.exit("chunkString"), i.exit(m), i.exit(d), i.exit(c), u(Y))
      : b < p && Y === 40
        ? (i.consume(Y), b++, G)
        : Y === 41
          ? (i.consume(Y), b--, G)
          : Y === null || Y === 32 || Y === 40 || Uo(Y)
            ? r(Y)
            : (i.consume(Y), Y === 92 ? F : G);
  }
  function F(Y) {
    return Y === 40 || Y === 41 || Y === 92 ? (i.consume(Y), G) : G(Y);
  }
}
function mm(i, u, r, c, f, s) {
  const d = this;
  let m = 0,
    y;
  return p;
  function p(x) {
    return (i.enter(c), i.enter(f), i.consume(x), i.exit(f), i.enter(s), b);
  }
  function b(x) {
    return m > 999 ||
      x === null ||
      x === 91 ||
      (x === 93 && !y) ||
      (x === 94 && !m && "_hiddenFootnoteSupport" in d.parser.constructs)
      ? r(x)
      : x === 93
        ? (i.exit(s), i.enter(f), i.consume(x), i.exit(f), i.exit(c), u)
        : st(x)
          ? (i.enter("lineEnding"), i.consume(x), i.exit("lineEnding"), b)
          : (i.enter("chunkString", { contentType: "string" }), v(x));
  }
  function v(x) {
    return x === null || x === 91 || x === 93 || st(x) || m++ > 999
      ? (i.exit("chunkString"), b(x))
      : (i.consume(x), y || (y = !Ut(x)), x === 92 ? T : v);
  }
  function T(x) {
    return x === 91 || x === 92 || x === 93 ? (i.consume(x), m++, v) : v(x);
  }
}
function gm(i, u, r, c, f, s) {
  let d;
  return m;
  function m(T) {
    return T === 34 || T === 39 || T === 40
      ? (i.enter(c),
        i.enter(f),
        i.consume(T),
        i.exit(f),
        (d = T === 40 ? 41 : T),
        y)
      : r(T);
  }
  function y(T) {
    return T === d
      ? (i.enter(f), i.consume(T), i.exit(f), i.exit(c), u)
      : (i.enter(s), p(T));
  }
  function p(T) {
    return T === d
      ? (i.exit(s), y(d))
      : T === null
        ? r(T)
        : st(T)
          ? (i.enter("lineEnding"),
            i.consume(T),
            i.exit("lineEnding"),
            Vt(i, p, "linePrefix"))
          : (i.enter("chunkString", { contentType: "string" }), b(T));
  }
  function b(T) {
    return T === d || T === null || st(T)
      ? (i.exit("chunkString"), p(T))
      : (i.consume(T), T === 92 ? v : b);
  }
  function v(T) {
    return T === d || T === 92 ? (i.consume(T), b) : b(T);
  }
}
function ma(i, u) {
  let r;
  return c;
  function c(f) {
    return st(f)
      ? (i.enter("lineEnding"), i.consume(f), i.exit("lineEnding"), (r = !0), c)
      : Ut(f)
        ? Vt(i, c, r ? "linePrefix" : "lineSuffix")(f)
        : u(f);
  }
}
const j0 = { name: "definition", tokenize: L0 },
  H0 = { partial: !0, tokenize: q0 };
function L0(i, u, r) {
  const c = this;
  let f;
  return s;
  function s(x) {
    return (i.enter("definition"), d(x));
  }
  function d(x) {
    return mm.call(
      c,
      i,
      m,
      r,
      "definitionLabel",
      "definitionLabelMarker",
      "definitionLabelString",
    )(x);
  }
  function m(x) {
    return (
      (f = hi(c.sliceSerialize(c.events[c.events.length - 1][1]).slice(1, -1))),
      x === 58
        ? (i.enter("definitionMarker"),
          i.consume(x),
          i.exit("definitionMarker"),
          y)
        : r(x)
    );
  }
  function y(x) {
    return Oe(x) ? ma(i, p)(x) : p(x);
  }
  function p(x) {
    return pm(
      i,
      b,
      r,
      "definitionDestination",
      "definitionDestinationLiteral",
      "definitionDestinationLiteralMarker",
      "definitionDestinationRaw",
      "definitionDestinationString",
    )(x);
  }
  function b(x) {
    return i.attempt(H0, v, v)(x);
  }
  function v(x) {
    return Ut(x) ? Vt(i, T, "whitespace")(x) : T(x);
  }
  function T(x) {
    return x === null || st(x)
      ? (i.exit("definition"), c.parser.defined.push(f), u(x))
      : r(x);
  }
}
function q0(i, u, r) {
  return c;
  function c(m) {
    return Oe(m) ? ma(i, f)(m) : r(m);
  }
  function f(m) {
    return gm(
      i,
      s,
      r,
      "definitionTitle",
      "definitionTitleMarker",
      "definitionTitleString",
    )(m);
  }
  function s(m) {
    return Ut(m) ? Vt(i, d, "whitespace")(m) : d(m);
  }
  function d(m) {
    return m === null || st(m) ? u(m) : r(m);
  }
}
const Y0 = { name: "hardBreakEscape", tokenize: G0 };
function G0(i, u, r) {
  return c;
  function c(s) {
    return (i.enter("hardBreakEscape"), i.consume(s), f);
  }
  function f(s) {
    return st(s) ? (i.exit("hardBreakEscape"), u(s)) : r(s);
  }
}
const X0 = { name: "headingAtx", resolve: Q0, tokenize: V0 };
function Q0(i, u) {
  let r = i.length - 2,
    c = 3,
    f,
    s;
  return (
    i[c][1].type === "whitespace" && (c += 2),
    r - 2 > c && i[r][1].type === "whitespace" && (r -= 2),
    i[r][1].type === "atxHeadingSequence" &&
      (c === r - 1 || (r - 4 > c && i[r - 2][1].type === "whitespace")) &&
      (r -= c + 1 === r ? 2 : 4),
    r > c &&
      ((f = { type: "atxHeadingText", start: i[c][1].start, end: i[r][1].end }),
      (s = {
        type: "chunkText",
        start: i[c][1].start,
        end: i[r][1].end,
        contentType: "text",
      }),
      cn(i, c, r - c + 1, [
        ["enter", f, u],
        ["enter", s, u],
        ["exit", s, u],
        ["exit", f, u],
      ])),
    i
  );
}
function V0(i, u, r) {
  let c = 0;
  return f;
  function f(b) {
    return (i.enter("atxHeading"), s(b));
  }
  function s(b) {
    return (i.enter("atxHeadingSequence"), d(b));
  }
  function d(b) {
    return b === 35 && c++ < 6
      ? (i.consume(b), d)
      : b === null || Oe(b)
        ? (i.exit("atxHeadingSequence"), m(b))
        : r(b);
  }
  function m(b) {
    return b === 35
      ? (i.enter("atxHeadingSequence"), y(b))
      : b === null || st(b)
        ? (i.exit("atxHeading"), u(b))
        : Ut(b)
          ? Vt(i, m, "whitespace")(b)
          : (i.enter("atxHeadingText"), p(b));
  }
  function y(b) {
    return b === 35 ? (i.consume(b), y) : (i.exit("atxHeadingSequence"), m(b));
  }
  function p(b) {
    return b === null || b === 35 || Oe(b)
      ? (i.exit("atxHeadingText"), m(b))
      : (i.consume(b), p);
  }
}
const Z0 = [
    "address",
    "article",
    "aside",
    "base",
    "basefont",
    "blockquote",
    "body",
    "caption",
    "center",
    "col",
    "colgroup",
    "dd",
    "details",
    "dialog",
    "dir",
    "div",
    "dl",
    "dt",
    "fieldset",
    "figcaption",
    "figure",
    "footer",
    "form",
    "frame",
    "frameset",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "head",
    "header",
    "hr",
    "html",
    "iframe",
    "legend",
    "li",
    "link",
    "main",
    "menu",
    "menuitem",
    "nav",
    "noframes",
    "ol",
    "optgroup",
    "option",
    "p",
    "param",
    "search",
    "section",
    "summary",
    "table",
    "tbody",
    "td",
    "tfoot",
    "th",
    "thead",
    "title",
    "tr",
    "track",
    "ul",
  ],
  _p = ["pre", "script", "style", "textarea"],
  K0 = { concrete: !0, name: "htmlFlow", resolveTo: I0, tokenize: W0 },
  J0 = { partial: !0, tokenize: P0 },
  F0 = { partial: !0, tokenize: $0 };
function I0(i) {
  let u = i.length;
  for (; u-- && !(i[u][0] === "enter" && i[u][1].type === "htmlFlow"); );
  return (
    u > 1 &&
      i[u - 2][1].type === "linePrefix" &&
      ((i[u][1].start = i[u - 2][1].start),
      (i[u + 1][1].start = i[u - 2][1].start),
      i.splice(u - 2, 2)),
    i
  );
}
function W0(i, u, r) {
  const c = this;
  let f, s, d, m, y;
  return p;
  function p(S) {
    return b(S);
  }
  function b(S) {
    return (i.enter("htmlFlow"), i.enter("htmlFlowData"), i.consume(S), v);
  }
  function v(S) {
    return S === 33
      ? (i.consume(S), T)
      : S === 47
        ? (i.consume(S), (s = !0), G)
        : S === 63
          ? (i.consume(S), (f = 3), c.interrupt ? u : E)
          : rn(S)
            ? (i.consume(S), (d = String.fromCharCode(S)), F)
            : r(S);
  }
  function T(S) {
    return S === 45
      ? (i.consume(S), (f = 2), x)
      : S === 91
        ? (i.consume(S), (f = 5), (m = 0), X)
        : rn(S)
          ? (i.consume(S), (f = 4), c.interrupt ? u : E)
          : r(S);
  }
  function x(S) {
    return S === 45 ? (i.consume(S), c.interrupt ? u : E) : r(S);
  }
  function X(S) {
    const I = "CDATA[";
    return S === I.charCodeAt(m++)
      ? (i.consume(S), m === I.length ? (c.interrupt ? u : $) : X)
      : r(S);
  }
  function G(S) {
    return rn(S) ? (i.consume(S), (d = String.fromCharCode(S)), F) : r(S);
  }
  function F(S) {
    if (S === null || S === 47 || S === 62 || Oe(S)) {
      const I = S === 47,
        ct = d.toLowerCase();
      return !I && !s && _p.includes(ct)
        ? ((f = 1), c.interrupt ? u(S) : $(S))
        : Z0.includes(d.toLowerCase())
          ? ((f = 6), I ? (i.consume(S), Y) : c.interrupt ? u(S) : $(S))
          : ((f = 7),
            c.interrupt && !c.parser.lazy[c.now().line]
              ? r(S)
              : s
                ? it(S)
                : K(S));
    }
    return S === 45 || Le(S)
      ? (i.consume(S), (d += String.fromCharCode(S)), F)
      : r(S);
  }
  function Y(S) {
    return S === 62 ? (i.consume(S), c.interrupt ? u : $) : r(S);
  }
  function it(S) {
    return Ut(S) ? (i.consume(S), it) : Et(S);
  }
  function K(S) {
    return S === 47
      ? (i.consume(S), Et)
      : S === 58 || S === 95 || rn(S)
        ? (i.consume(S), mt)
        : Ut(S)
          ? (i.consume(S), K)
          : Et(S);
  }
  function mt(S) {
    return S === 45 || S === 46 || S === 58 || S === 95 || Le(S)
      ? (i.consume(S), mt)
      : yt(S);
  }
  function yt(S) {
    return S === 61 ? (i.consume(S), H) : Ut(S) ? (i.consume(S), yt) : K(S);
  }
  function H(S) {
    return S === null || S === 60 || S === 61 || S === 62 || S === 96
      ? r(S)
      : S === 34 || S === 39
        ? (i.consume(S), (y = S), W)
        : Ut(S)
          ? (i.consume(S), H)
          : ht(S);
  }
  function W(S) {
    return S === y
      ? (i.consume(S), (y = null), pt)
      : S === null || st(S)
        ? r(S)
        : (i.consume(S), W);
  }
  function ht(S) {
    return S === null ||
      S === 34 ||
      S === 39 ||
      S === 47 ||
      S === 60 ||
      S === 61 ||
      S === 62 ||
      S === 96 ||
      Oe(S)
      ? yt(S)
      : (i.consume(S), ht);
  }
  function pt(S) {
    return S === 47 || S === 62 || Ut(S) ? K(S) : r(S);
  }
  function Et(S) {
    return S === 62 ? (i.consume(S), tt) : r(S);
  }
  function tt(S) {
    return S === null || st(S) ? $(S) : Ut(S) ? (i.consume(S), tt) : r(S);
  }
  function $(S) {
    return S === 45 && f === 2
      ? (i.consume(S), M)
      : S === 60 && f === 1
        ? (i.consume(S), B)
        : S === 62 && f === 4
          ? (i.consume(S), A)
          : S === 63 && f === 3
            ? (i.consume(S), E)
            : S === 93 && f === 5
              ? (i.consume(S), xt)
              : st(S) && (f === 6 || f === 7)
                ? (i.exit("htmlFlowData"), i.check(J0, U, _t)(S))
                : S === null || st(S)
                  ? (i.exit("htmlFlowData"), _t(S))
                  : (i.consume(S), $);
  }
  function _t(S) {
    return i.check(F0, lt, U)(S);
  }
  function lt(S) {
    return (i.enter("lineEnding"), i.consume(S), i.exit("lineEnding"), Q);
  }
  function Q(S) {
    return S === null || st(S) ? _t(S) : (i.enter("htmlFlowData"), $(S));
  }
  function M(S) {
    return S === 45 ? (i.consume(S), E) : $(S);
  }
  function B(S) {
    return S === 47 ? (i.consume(S), (d = ""), P) : $(S);
  }
  function P(S) {
    if (S === 62) {
      const I = d.toLowerCase();
      return _p.includes(I) ? (i.consume(S), A) : $(S);
    }
    return rn(S) && d.length < 8
      ? (i.consume(S), (d += String.fromCharCode(S)), P)
      : $(S);
  }
  function xt(S) {
    return S === 93 ? (i.consume(S), E) : $(S);
  }
  function E(S) {
    return S === 62
      ? (i.consume(S), A)
      : S === 45 && f === 2
        ? (i.consume(S), E)
        : $(S);
  }
  function A(S) {
    return S === null || st(S)
      ? (i.exit("htmlFlowData"), U(S))
      : (i.consume(S), A);
  }
  function U(S) {
    return (i.exit("htmlFlow"), u(S));
  }
}
function $0(i, u, r) {
  const c = this;
  return f;
  function f(d) {
    return st(d)
      ? (i.enter("lineEnding"), i.consume(d), i.exit("lineEnding"), s)
      : r(d);
  }
  function s(d) {
    return c.parser.lazy[c.now().line] ? r(d) : u(d);
  }
}
function P0(i, u, r) {
  return c;
  function c(f) {
    return (
      i.enter("lineEnding"),
      i.consume(f),
      i.exit("lineEnding"),
      i.attempt(Zu, u, r)
    );
  }
}
const tb = { name: "htmlText", tokenize: eb };
function eb(i, u, r) {
  const c = this;
  let f, s, d;
  return m;
  function m(E) {
    return (i.enter("htmlText"), i.enter("htmlTextData"), i.consume(E), y);
  }
  function y(E) {
    return E === 33
      ? (i.consume(E), p)
      : E === 47
        ? (i.consume(E), yt)
        : E === 63
          ? (i.consume(E), K)
          : rn(E)
            ? (i.consume(E), ht)
            : r(E);
  }
  function p(E) {
    return E === 45
      ? (i.consume(E), b)
      : E === 91
        ? (i.consume(E), (s = 0), X)
        : rn(E)
          ? (i.consume(E), it)
          : r(E);
  }
  function b(E) {
    return E === 45 ? (i.consume(E), x) : r(E);
  }
  function v(E) {
    return E === null
      ? r(E)
      : E === 45
        ? (i.consume(E), T)
        : st(E)
          ? ((d = v), B(E))
          : (i.consume(E), v);
  }
  function T(E) {
    return E === 45 ? (i.consume(E), x) : v(E);
  }
  function x(E) {
    return E === 62 ? M(E) : E === 45 ? T(E) : v(E);
  }
  function X(E) {
    const A = "CDATA[";
    return E === A.charCodeAt(s++)
      ? (i.consume(E), s === A.length ? G : X)
      : r(E);
  }
  function G(E) {
    return E === null
      ? r(E)
      : E === 93
        ? (i.consume(E), F)
        : st(E)
          ? ((d = G), B(E))
          : (i.consume(E), G);
  }
  function F(E) {
    return E === 93 ? (i.consume(E), Y) : G(E);
  }
  function Y(E) {
    return E === 62 ? M(E) : E === 93 ? (i.consume(E), Y) : G(E);
  }
  function it(E) {
    return E === null || E === 62
      ? M(E)
      : st(E)
        ? ((d = it), B(E))
        : (i.consume(E), it);
  }
  function K(E) {
    return E === null
      ? r(E)
      : E === 63
        ? (i.consume(E), mt)
        : st(E)
          ? ((d = K), B(E))
          : (i.consume(E), K);
  }
  function mt(E) {
    return E === 62 ? M(E) : K(E);
  }
  function yt(E) {
    return rn(E) ? (i.consume(E), H) : r(E);
  }
  function H(E) {
    return E === 45 || Le(E) ? (i.consume(E), H) : W(E);
  }
  function W(E) {
    return st(E) ? ((d = W), B(E)) : Ut(E) ? (i.consume(E), W) : M(E);
  }
  function ht(E) {
    return E === 45 || Le(E)
      ? (i.consume(E), ht)
      : E === 47 || E === 62 || Oe(E)
        ? pt(E)
        : r(E);
  }
  function pt(E) {
    return E === 47
      ? (i.consume(E), M)
      : E === 58 || E === 95 || rn(E)
        ? (i.consume(E), Et)
        : st(E)
          ? ((d = pt), B(E))
          : Ut(E)
            ? (i.consume(E), pt)
            : M(E);
  }
  function Et(E) {
    return E === 45 || E === 46 || E === 58 || E === 95 || Le(E)
      ? (i.consume(E), Et)
      : tt(E);
  }
  function tt(E) {
    return E === 61
      ? (i.consume(E), $)
      : st(E)
        ? ((d = tt), B(E))
        : Ut(E)
          ? (i.consume(E), tt)
          : pt(E);
  }
  function $(E) {
    return E === null || E === 60 || E === 61 || E === 62 || E === 96
      ? r(E)
      : E === 34 || E === 39
        ? (i.consume(E), (f = E), _t)
        : st(E)
          ? ((d = $), B(E))
          : Ut(E)
            ? (i.consume(E), $)
            : (i.consume(E), lt);
  }
  function _t(E) {
    return E === f
      ? (i.consume(E), (f = void 0), Q)
      : E === null
        ? r(E)
        : st(E)
          ? ((d = _t), B(E))
          : (i.consume(E), _t);
  }
  function lt(E) {
    return E === null ||
      E === 34 ||
      E === 39 ||
      E === 60 ||
      E === 61 ||
      E === 96
      ? r(E)
      : E === 47 || E === 62 || Oe(E)
        ? pt(E)
        : (i.consume(E), lt);
  }
  function Q(E) {
    return E === 47 || E === 62 || Oe(E) ? pt(E) : r(E);
  }
  function M(E) {
    return E === 62
      ? (i.consume(E), i.exit("htmlTextData"), i.exit("htmlText"), u)
      : r(E);
  }
  function B(E) {
    return (
      i.exit("htmlTextData"),
      i.enter("lineEnding"),
      i.consume(E),
      i.exit("lineEnding"),
      P
    );
  }
  function P(E) {
    return Ut(E)
      ? Vt(
          i,
          xt,
          "linePrefix",
          c.parser.constructs.disable.null.includes("codeIndented")
            ? void 0
            : 4,
        )(E)
      : xt(E);
  }
  function xt(E) {
    return (i.enter("htmlTextData"), d(E));
  }
}
const Io = { name: "labelEnd", resolveAll: ab, resolveTo: ub, tokenize: rb },
  nb = { tokenize: cb },
  lb = { tokenize: ob },
  ib = { tokenize: fb };
function ab(i) {
  let u = -1;
  const r = [];
  for (; ++u < i.length; ) {
    const c = i[u][1];
    if (
      (r.push(i[u]),
      c.type === "labelImage" ||
        c.type === "labelLink" ||
        c.type === "labelEnd")
    ) {
      const f = c.type === "labelImage" ? 4 : 2;
      ((c.type = "data"), (u += f));
    }
  }
  return (i.length !== r.length && cn(i, 0, i.length, r), i);
}
function ub(i, u) {
  let r = i.length,
    c = 0,
    f,
    s,
    d,
    m;
  for (; r--; )
    if (((f = i[r][1]), s)) {
      if (f.type === "link" || (f.type === "labelLink" && f._inactive)) break;
      i[r][0] === "enter" && f.type === "labelLink" && (f._inactive = !0);
    } else if (d) {
      if (
        i[r][0] === "enter" &&
        (f.type === "labelImage" || f.type === "labelLink") &&
        !f._balanced &&
        ((s = r), f.type !== "labelLink")
      ) {
        c = 2;
        break;
      }
    } else f.type === "labelEnd" && (d = r);
  const y = {
      type: i[s][1].type === "labelLink" ? "link" : "image",
      start: { ...i[s][1].start },
      end: { ...i[i.length - 1][1].end },
    },
    p = { type: "label", start: { ...i[s][1].start }, end: { ...i[d][1].end } },
    b = {
      type: "labelText",
      start: { ...i[s + c + 2][1].end },
      end: { ...i[d - 2][1].start },
    };
  return (
    (m = [
      ["enter", y, u],
      ["enter", p, u],
    ]),
    (m = Ie(m, i.slice(s + 1, s + c + 3))),
    (m = Ie(m, [["enter", b, u]])),
    (m = Ie(
      m,
      Fo(u.parser.constructs.insideSpan.null, i.slice(s + c + 4, d - 3), u),
    )),
    (m = Ie(m, [["exit", b, u], i[d - 2], i[d - 1], ["exit", p, u]])),
    (m = Ie(m, i.slice(d + 1))),
    (m = Ie(m, [["exit", y, u]])),
    cn(i, s, i.length, m),
    i
  );
}
function rb(i, u, r) {
  const c = this;
  let f = c.events.length,
    s,
    d;
  for (; f--; )
    if (
      (c.events[f][1].type === "labelImage" ||
        c.events[f][1].type === "labelLink") &&
      !c.events[f][1]._balanced
    ) {
      s = c.events[f][1];
      break;
    }
  return m;
  function m(T) {
    return s
      ? s._inactive
        ? v(T)
        : ((d = c.parser.defined.includes(
            hi(c.sliceSerialize({ start: s.end, end: c.now() })),
          )),
          i.enter("labelEnd"),
          i.enter("labelMarker"),
          i.consume(T),
          i.exit("labelMarker"),
          i.exit("labelEnd"),
          y)
      : r(T);
  }
  function y(T) {
    return T === 40
      ? i.attempt(nb, b, d ? b : v)(T)
      : T === 91
        ? i.attempt(lb, b, d ? p : v)(T)
        : d
          ? b(T)
          : v(T);
  }
  function p(T) {
    return i.attempt(ib, b, v)(T);
  }
  function b(T) {
    return u(T);
  }
  function v(T) {
    return ((s._balanced = !0), r(T));
  }
}
function cb(i, u, r) {
  return c;
  function c(v) {
    return (
      i.enter("resource"),
      i.enter("resourceMarker"),
      i.consume(v),
      i.exit("resourceMarker"),
      f
    );
  }
  function f(v) {
    return Oe(v) ? ma(i, s)(v) : s(v);
  }
  function s(v) {
    return v === 41
      ? b(v)
      : pm(
          i,
          d,
          m,
          "resourceDestination",
          "resourceDestinationLiteral",
          "resourceDestinationLiteralMarker",
          "resourceDestinationRaw",
          "resourceDestinationString",
          32,
        )(v);
  }
  function d(v) {
    return Oe(v) ? ma(i, y)(v) : b(v);
  }
  function m(v) {
    return r(v);
  }
  function y(v) {
    return v === 34 || v === 39 || v === 40
      ? gm(
          i,
          p,
          r,
          "resourceTitle",
          "resourceTitleMarker",
          "resourceTitleString",
        )(v)
      : b(v);
  }
  function p(v) {
    return Oe(v) ? ma(i, b)(v) : b(v);
  }
  function b(v) {
    return v === 41
      ? (i.enter("resourceMarker"),
        i.consume(v),
        i.exit("resourceMarker"),
        i.exit("resource"),
        u)
      : r(v);
  }
}
function ob(i, u, r) {
  const c = this;
  return f;
  function f(m) {
    return mm.call(
      c,
      i,
      s,
      d,
      "reference",
      "referenceMarker",
      "referenceString",
    )(m);
  }
  function s(m) {
    return c.parser.defined.includes(
      hi(c.sliceSerialize(c.events[c.events.length - 1][1]).slice(1, -1)),
    )
      ? u(m)
      : r(m);
  }
  function d(m) {
    return r(m);
  }
}
function fb(i, u, r) {
  return c;
  function c(s) {
    return (
      i.enter("reference"),
      i.enter("referenceMarker"),
      i.consume(s),
      i.exit("referenceMarker"),
      f
    );
  }
  function f(s) {
    return s === 93
      ? (i.enter("referenceMarker"),
        i.consume(s),
        i.exit("referenceMarker"),
        i.exit("reference"),
        u)
      : r(s);
  }
}
const sb = { name: "labelStartImage", resolveAll: Io.resolveAll, tokenize: hb };
function hb(i, u, r) {
  const c = this;
  return f;
  function f(m) {
    return (
      i.enter("labelImage"),
      i.enter("labelImageMarker"),
      i.consume(m),
      i.exit("labelImageMarker"),
      s
    );
  }
  function s(m) {
    return m === 91
      ? (i.enter("labelMarker"),
        i.consume(m),
        i.exit("labelMarker"),
        i.exit("labelImage"),
        d)
      : r(m);
  }
  function d(m) {
    return m === 94 && "_hiddenFootnoteSupport" in c.parser.constructs
      ? r(m)
      : u(m);
  }
}
const db = { name: "labelStartLink", resolveAll: Io.resolveAll, tokenize: pb };
function pb(i, u, r) {
  const c = this;
  return f;
  function f(d) {
    return (
      i.enter("labelLink"),
      i.enter("labelMarker"),
      i.consume(d),
      i.exit("labelMarker"),
      i.exit("labelLink"),
      s
    );
  }
  function s(d) {
    return d === 94 && "_hiddenFootnoteSupport" in c.parser.constructs
      ? r(d)
      : u(d);
  }
}
const Eo = { name: "lineEnding", tokenize: mb };
function mb(i, u) {
  return r;
  function r(c) {
    return (
      i.enter("lineEnding"),
      i.consume(c),
      i.exit("lineEnding"),
      Vt(i, u, "linePrefix")
    );
  }
}
const Gu = { name: "thematicBreak", tokenize: gb };
function gb(i, u, r) {
  let c = 0,
    f;
  return s;
  function s(p) {
    return (i.enter("thematicBreak"), d(p));
  }
  function d(p) {
    return ((f = p), m(p));
  }
  function m(p) {
    return p === f
      ? (i.enter("thematicBreakSequence"), y(p))
      : c >= 3 && (p === null || st(p))
        ? (i.exit("thematicBreak"), u(p))
        : r(p);
  }
  function y(p) {
    return p === f
      ? (i.consume(p), c++, y)
      : (i.exit("thematicBreakSequence"),
        Ut(p) ? Vt(i, m, "whitespace")(p) : m(p));
  }
}
const _e = {
    continuation: { tokenize: Sb },
    exit: Eb,
    name: "list",
    tokenize: vb,
  },
  yb = { partial: !0, tokenize: zb },
  bb = { partial: !0, tokenize: xb };
function vb(i, u, r) {
  const c = this,
    f = c.events[c.events.length - 1];
  let s =
      f && f[1].type === "linePrefix"
        ? f[2].sliceSerialize(f[1], !0).length
        : 0,
    d = 0;
  return m;
  function m(x) {
    const X =
      c.containerState.type ||
      (x === 42 || x === 43 || x === 45 ? "listUnordered" : "listOrdered");
    if (
      X === "listUnordered"
        ? !c.containerState.marker || x === c.containerState.marker
        : Bo(x)
    ) {
      if (
        (c.containerState.type ||
          ((c.containerState.type = X), i.enter(X, { _container: !0 })),
        X === "listUnordered")
      )
        return (
          i.enter("listItemPrefix"),
          x === 42 || x === 45 ? i.check(Gu, r, p)(x) : p(x)
        );
      if (!c.interrupt || x === 49)
        return (i.enter("listItemPrefix"), i.enter("listItemValue"), y(x));
    }
    return r(x);
  }
  function y(x) {
    return Bo(x) && ++d < 10
      ? (i.consume(x), y)
      : (!c.interrupt || d < 2) &&
          (c.containerState.marker
            ? x === c.containerState.marker
            : x === 41 || x === 46)
        ? (i.exit("listItemValue"), p(x))
        : r(x);
  }
  function p(x) {
    return (
      i.enter("listItemMarker"),
      i.consume(x),
      i.exit("listItemMarker"),
      (c.containerState.marker = c.containerState.marker || x),
      i.check(Zu, c.interrupt ? r : b, i.attempt(yb, T, v))
    );
  }
  function b(x) {
    return ((c.containerState.initialBlankLine = !0), s++, T(x));
  }
  function v(x) {
    return Ut(x)
      ? (i.enter("listItemPrefixWhitespace"),
        i.consume(x),
        i.exit("listItemPrefixWhitespace"),
        T)
      : r(x);
  }
  function T(x) {
    return (
      (c.containerState.size =
        s + c.sliceSerialize(i.exit("listItemPrefix"), !0).length),
      u(x)
    );
  }
}
function Sb(i, u, r) {
  const c = this;
  return ((c.containerState._closeFlow = void 0), i.check(Zu, f, s));
  function f(m) {
    return (
      (c.containerState.furtherBlankLines =
        c.containerState.furtherBlankLines ||
        c.containerState.initialBlankLine),
      Vt(i, u, "listItemIndent", c.containerState.size + 1)(m)
    );
  }
  function s(m) {
    return c.containerState.furtherBlankLines || !Ut(m)
      ? ((c.containerState.furtherBlankLines = void 0),
        (c.containerState.initialBlankLine = void 0),
        d(m))
      : ((c.containerState.furtherBlankLines = void 0),
        (c.containerState.initialBlankLine = void 0),
        i.attempt(bb, u, d)(m));
  }
  function d(m) {
    return (
      (c.containerState._closeFlow = !0),
      (c.interrupt = void 0),
      Vt(
        i,
        i.attempt(_e, u, r),
        "linePrefix",
        c.parser.constructs.disable.null.includes("codeIndented") ? void 0 : 4,
      )(m)
    );
  }
}
function xb(i, u, r) {
  const c = this;
  return Vt(i, f, "listItemIndent", c.containerState.size + 1);
  function f(s) {
    const d = c.events[c.events.length - 1];
    return d &&
      d[1].type === "listItemIndent" &&
      d[2].sliceSerialize(d[1], !0).length === c.containerState.size
      ? u(s)
      : r(s);
  }
}
function Eb(i) {
  i.exit(this.containerState.type);
}
function zb(i, u, r) {
  const c = this;
  return Vt(
    i,
    f,
    "listItemPrefixWhitespace",
    c.parser.constructs.disable.null.includes("codeIndented") ? void 0 : 5,
  );
  function f(s) {
    const d = c.events[c.events.length - 1];
    return !Ut(s) && d && d[1].type === "listItemPrefixWhitespace"
      ? u(s)
      : r(s);
  }
}
const Op = { name: "setextUnderline", resolveTo: Tb, tokenize: Ab };
function Tb(i, u) {
  let r = i.length,
    c,
    f,
    s;
  for (; r--; )
    if (i[r][0] === "enter") {
      if (i[r][1].type === "content") {
        c = r;
        break;
      }
      i[r][1].type === "paragraph" && (f = r);
    } else
      (i[r][1].type === "content" && i.splice(r, 1),
        !s && i[r][1].type === "definition" && (s = r));
  const d = {
    type: "setextHeading",
    start: { ...i[c][1].start },
    end: { ...i[i.length - 1][1].end },
  };
  return (
    (i[f][1].type = "setextHeadingText"),
    s
      ? (i.splice(f, 0, ["enter", d, u]),
        i.splice(s + 1, 0, ["exit", i[c][1], u]),
        (i[c][1].end = { ...i[s][1].end }))
      : (i[c][1] = d),
    i.push(["exit", d, u]),
    i
  );
}
function Ab(i, u, r) {
  const c = this;
  let f;
  return s;
  function s(p) {
    let b = c.events.length,
      v;
    for (; b--; )
      if (
        c.events[b][1].type !== "lineEnding" &&
        c.events[b][1].type !== "linePrefix" &&
        c.events[b][1].type !== "content"
      ) {
        v = c.events[b][1].type === "paragraph";
        break;
      }
    return !c.parser.lazy[c.now().line] && (c.interrupt || v)
      ? (i.enter("setextHeadingLine"), (f = p), d(p))
      : r(p);
  }
  function d(p) {
    return (i.enter("setextHeadingLineSequence"), m(p));
  }
  function m(p) {
    return p === f
      ? (i.consume(p), m)
      : (i.exit("setextHeadingLineSequence"),
        Ut(p) ? Vt(i, y, "lineSuffix")(p) : y(p));
  }
  function y(p) {
    return p === null || st(p) ? (i.exit("setextHeadingLine"), u(p)) : r(p);
  }
}
const Cb = { tokenize: _b };
function _b(i) {
  const u = this,
    r = i.attempt(
      Zu,
      c,
      i.attempt(
        this.parser.constructs.flowInitial,
        f,
        Vt(
          i,
          i.attempt(this.parser.constructs.flow, f, i.attempt(w0, f)),
          "linePrefix",
        ),
      ),
    );
  return r;
  function c(s) {
    if (s === null) {
      i.consume(s);
      return;
    }
    return (
      i.enter("lineEndingBlank"),
      i.consume(s),
      i.exit("lineEndingBlank"),
      (u.currentConstruct = void 0),
      r
    );
  }
  function f(s) {
    if (s === null) {
      i.consume(s);
      return;
    }
    return (
      i.enter("lineEnding"),
      i.consume(s),
      i.exit("lineEnding"),
      (u.currentConstruct = void 0),
      r
    );
  }
}
const Ob = { resolveAll: bm() },
  Db = ym("string"),
  Mb = ym("text");
function ym(i) {
  return { resolveAll: bm(i === "text" ? kb : void 0), tokenize: u };
  function u(r) {
    const c = this,
      f = this.parser.constructs[i],
      s = r.attempt(f, d, m);
    return d;
    function d(b) {
      return p(b) ? s(b) : m(b);
    }
    function m(b) {
      if (b === null) {
        r.consume(b);
        return;
      }
      return (r.enter("data"), r.consume(b), y);
    }
    function y(b) {
      return p(b) ? (r.exit("data"), s(b)) : (r.consume(b), y);
    }
    function p(b) {
      if (b === null) return !0;
      const v = f[b];
      let T = -1;
      if (v)
        for (; ++T < v.length; ) {
          const x = v[T];
          if (!x.previous || x.previous.call(c, c.previous)) return !0;
        }
      return !1;
    }
  }
}
function bm(i) {
  return u;
  function u(r, c) {
    let f = -1,
      s;
    for (; ++f <= r.length; )
      s === void 0
        ? r[f] && r[f][1].type === "data" && ((s = f), f++)
        : (!r[f] || r[f][1].type !== "data") &&
          (f !== s + 2 &&
            ((r[s][1].end = r[f - 1][1].end),
            r.splice(s + 2, f - s - 2),
            (f = s + 2)),
          (s = void 0));
    return i ? i(r, c) : r;
  }
}
function kb(i, u) {
  let r = 0;
  for (; ++r <= i.length; )
    if (
      (r === i.length || i[r][1].type === "lineEnding") &&
      i[r - 1][1].type === "data"
    ) {
      const c = i[r - 1][1],
        f = u.sliceStream(c);
      let s = f.length,
        d = -1,
        m = 0,
        y;
      for (; s--; ) {
        const p = f[s];
        if (typeof p == "string") {
          for (d = p.length; p.charCodeAt(d - 1) === 32; ) (m++, d--);
          if (d) break;
          d = -1;
        } else if (p === -2) ((y = !0), m++);
        else if (p !== -1) {
          s++;
          break;
        }
      }
      if ((u._contentTypeTextTrailing && r === i.length && (m = 0), m)) {
        const p = {
          type:
            r === i.length || y || m < 2 ? "lineSuffix" : "hardBreakTrailing",
          start: {
            _bufferIndex: s ? d : c.start._bufferIndex + d,
            _index: c.start._index + s,
            line: c.end.line,
            column: c.end.column - m,
            offset: c.end.offset - m,
          },
          end: { ...c.end },
        };
        ((c.end = { ...p.start }),
          c.start.offset === c.end.offset
            ? Object.assign(c, p)
            : (i.splice(r, 0, ["enter", p, u], ["exit", p, u]), (r += 2)));
      }
      r++;
    }
  return i;
}
const wb = {
    42: _e,
    43: _e,
    45: _e,
    48: _e,
    49: _e,
    50: _e,
    51: _e,
    52: _e,
    53: _e,
    54: _e,
    55: _e,
    56: _e,
    57: _e,
    62: fm,
  },
  Nb = { 91: j0 },
  Rb = { [-2]: xo, [-1]: xo, 32: xo },
  Ub = {
    35: X0,
    42: Gu,
    45: [Op, Gu],
    60: K0,
    61: Op,
    95: Gu,
    96: Cp,
    126: Cp,
  },
  Bb = { 38: hm, 92: sm },
  jb = {
    [-5]: Eo,
    [-4]: Eo,
    [-3]: Eo,
    33: sb,
    38: hm,
    42: jo,
    60: [d0, tb],
    91: db,
    92: [Y0, sm],
    93: Io,
    95: jo,
    96: C0,
  },
  Hb = { null: [jo, Ob] },
  Lb = { null: [42, 95] },
  qb = { null: [] },
  Yb = Object.freeze(
    Object.defineProperty(
      {
        __proto__: null,
        attentionMarkers: Lb,
        contentInitial: Nb,
        disable: qb,
        document: wb,
        flow: Ub,
        flowInitial: Rb,
        insideSpan: Hb,
        string: Bb,
        text: jb,
      },
      Symbol.toStringTag,
      { value: "Module" },
    ),
  );
function Gb(i, u, r) {
  let c = {
    _bufferIndex: -1,
    _index: 0,
    line: (r && r.line) || 1,
    column: (r && r.column) || 1,
    offset: (r && r.offset) || 0,
  };
  const f = {},
    s = [];
  let d = [],
    m = [];
  const y = {
      attempt: W(yt),
      check: W(H),
      consume: it,
      enter: K,
      exit: mt,
      interrupt: W(H, { interrupt: !0 }),
    },
    p = {
      code: null,
      containerState: {},
      defineSkip: G,
      events: [],
      now: X,
      parser: i,
      previous: null,
      sliceSerialize: T,
      sliceStream: x,
      write: v,
    };
  let b = u.tokenize.call(p, y);
  return (u.resolveAll && s.push(u), p);
  function v(tt) {
    return (
      (d = Ie(d, tt)),
      F(),
      d[d.length - 1] !== null
        ? []
        : (ht(u, 0), (p.events = Fo(s, p.events, p)), p.events)
    );
  }
  function T(tt, $) {
    return Qb(x(tt), $);
  }
  function x(tt) {
    return Xb(d, tt);
  }
  function X() {
    const { _bufferIndex: tt, _index: $, line: _t, column: lt, offset: Q } = c;
    return { _bufferIndex: tt, _index: $, line: _t, column: lt, offset: Q };
  }
  function G(tt) {
    ((f[tt.line] = tt.column), Et());
  }
  function F() {
    let tt;
    for (; c._index < d.length; ) {
      const $ = d[c._index];
      if (typeof $ == "string")
        for (
          tt = c._index, c._bufferIndex < 0 && (c._bufferIndex = 0);
          c._index === tt && c._bufferIndex < $.length;
        )
          Y($.charCodeAt(c._bufferIndex));
      else Y($);
    }
  }
  function Y(tt) {
    b = b(tt);
  }
  function it(tt) {
    (st(tt)
      ? (c.line++, (c.column = 1), (c.offset += tt === -3 ? 2 : 1), Et())
      : tt !== -1 && (c.column++, c.offset++),
      c._bufferIndex < 0
        ? c._index++
        : (c._bufferIndex++,
          c._bufferIndex === d[c._index].length &&
            ((c._bufferIndex = -1), c._index++)),
      (p.previous = tt));
  }
  function K(tt, $) {
    const _t = $ || {};
    return (
      (_t.type = tt),
      (_t.start = X()),
      p.events.push(["enter", _t, p]),
      m.push(_t),
      _t
    );
  }
  function mt(tt) {
    const $ = m.pop();
    return (($.end = X()), p.events.push(["exit", $, p]), $);
  }
  function yt(tt, $) {
    ht(tt, $.from);
  }
  function H(tt, $) {
    $.restore();
  }
  function W(tt, $) {
    return _t;
    function _t(lt, Q, M) {
      let B, P, xt, E;
      return Array.isArray(lt) ? U(lt) : "tokenize" in lt ? U([lt]) : A(lt);
      function A(at) {
        return zt;
        function zt(V) {
          const ut = V !== null && at[V],
            kt = V !== null && at.null,
            me = [
              ...(Array.isArray(ut) ? ut : ut ? [ut] : []),
              ...(Array.isArray(kt) ? kt : kt ? [kt] : []),
            ];
          return U(me)(V);
        }
      }
      function U(at) {
        return ((B = at), (P = 0), at.length === 0 ? M : S(at[P]));
      }
      function S(at) {
        return zt;
        function zt(V) {
          return (
            (E = pt()),
            (xt = at),
            at.partial || (p.currentConstruct = at),
            at.name && p.parser.constructs.disable.null.includes(at.name)
              ? ct()
              : at.tokenize.call(
                  $ ? Object.assign(Object.create(p), $) : p,
                  y,
                  I,
                  ct,
                )(V)
          );
        }
      }
      function I(at) {
        return (tt(xt, E), Q);
      }
      function ct(at) {
        return (E.restore(), ++P < B.length ? S(B[P]) : M);
      }
    }
  }
  function ht(tt, $) {
    (tt.resolveAll && !s.includes(tt) && s.push(tt),
      tt.resolve &&
        cn(p.events, $, p.events.length - $, tt.resolve(p.events.slice($), p)),
      tt.resolveTo && (p.events = tt.resolveTo(p.events, p)));
  }
  function pt() {
    const tt = X(),
      $ = p.previous,
      _t = p.currentConstruct,
      lt = p.events.length,
      Q = Array.from(m);
    return { from: lt, restore: M };
    function M() {
      ((c = tt),
        (p.previous = $),
        (p.currentConstruct = _t),
        (p.events.length = lt),
        (m = Q),
        Et());
    }
  }
  function Et() {
    c.line in f &&
      c.column < 2 &&
      ((c.column = f[c.line]), (c.offset += f[c.line] - 1));
  }
}
function Xb(i, u) {
  const r = u.start._index,
    c = u.start._bufferIndex,
    f = u.end._index,
    s = u.end._bufferIndex;
  let d;
  if (r === f) d = [i[r].slice(c, s)];
  else {
    if (((d = i.slice(r, f)), c > -1)) {
      const m = d[0];
      typeof m == "string" ? (d[0] = m.slice(c)) : d.shift();
    }
    s > 0 && d.push(i[f].slice(0, s));
  }
  return d;
}
function Qb(i, u) {
  let r = -1;
  const c = [];
  let f;
  for (; ++r < i.length; ) {
    const s = i[r];
    let d;
    if (typeof s == "string") d = s;
    else
      switch (s) {
        case -5: {
          d = "\r";
          break;
        }
        case -4: {
          d = `
`;
          break;
        }
        case -3: {
          d = `\r
`;
          break;
        }
        case -2: {
          d = u ? " " : "	";
          break;
        }
        case -1: {
          if (!u && f) continue;
          d = " ";
          break;
        }
        default:
          d = String.fromCharCode(s);
      }
    ((f = s === -2), c.push(d));
  }
  return c.join("");
}
function Vb(i) {
  const c = {
    constructs: $1([Yb, ...((i || {}).extensions || [])]),
    content: f(u0),
    defined: [],
    document: f(c0),
    flow: f(Cb),
    lazy: {},
    string: f(Db),
    text: f(Mb),
  };
  return c;
  function f(s) {
    return d;
    function d(m) {
      return Gb(c, s, m);
    }
  }
}
function Zb(i) {
  for (; !dm(i); );
  return i;
}
const Dp = /[\0\t\n\r]/g;
function Kb() {
  let i = 1,
    u = "",
    r = !0,
    c;
  return f;
  function f(s, d, m) {
    const y = [];
    let p, b, v, T, x;
    for (
      s =
        u +
        (typeof s == "string"
          ? s.toString()
          : new TextDecoder(d || void 0).decode(s)),
        v = 0,
        u = "",
        r && (s.charCodeAt(0) === 65279 && v++, (r = void 0));
      v < s.length;
    ) {
      if (
        ((Dp.lastIndex = v),
        (p = Dp.exec(s)),
        (T = p && p.index !== void 0 ? p.index : s.length),
        (x = s.charCodeAt(T)),
        !p)
      ) {
        u = s.slice(v);
        break;
      }
      if (x === 10 && v === T && c) (y.push(-3), (c = void 0));
      else
        switch (
          (c && (y.push(-5), (c = void 0)),
          v < T && (y.push(s.slice(v, T)), (i += T - v)),
          x)
        ) {
          case 0: {
            (y.push(65533), i++);
            break;
          }
          case 9: {
            for (b = Math.ceil(i / 4) * 4, y.push(-2); i++ < b; ) y.push(-1);
            break;
          }
          case 10: {
            (y.push(-4), (i = 1));
            break;
          }
          default:
            ((c = !0), (i = 1));
        }
      v = T + 1;
    }
    return (m && (c && y.push(-5), u && y.push(u), y.push(null)), y);
  }
}
const Jb = /\\([!-/:-@[-`{-~])|&(#(?:\d{1,7}|x[\da-f]{1,6})|[\da-z]{1,31});/gi;
function Fb(i) {
  return i.replace(Jb, Ib);
}
function Ib(i, u, r) {
  if (u) return u;
  if (r.charCodeAt(0) === 35) {
    const f = r.charCodeAt(1),
      s = f === 120 || f === 88;
    return om(r.slice(s ? 2 : 1), s ? 16 : 10);
  }
  return Jo(r) || i;
}
const vm = {}.hasOwnProperty;
function Wb(i, u, r) {
  return (
    typeof u != "string" && ((r = u), (u = void 0)),
    $b(r)(
      Zb(
        Vb(r)
          .document()
          .write(Kb()(i, u, !0)),
      ),
    )
  );
}
function $b(i) {
  const u = {
    transforms: [],
    canContainEols: ["emphasis", "fragment", "heading", "paragraph", "strong"],
    enter: {
      autolink: s(zl),
      autolinkProtocol: pt,
      autolinkEmail: pt,
      atxHeading: s(xl),
      blockQuote: s(kt),
      characterEscape: pt,
      characterReference: pt,
      codeFenced: s(me),
      codeFencedFenceInfo: d,
      codeFencedFenceMeta: d,
      codeIndented: s(me, d),
      codeText: s(mi, d),
      codeTextData: pt,
      data: pt,
      codeFlowValue: pt,
      definition: s(Sa),
      definitionDestinationString: d,
      definitionLabelString: d,
      definitionTitleString: d,
      emphasis: s(on),
      hardBreakEscape: s(El),
      hardBreakTrailing: s(El),
      htmlFlow: s(xa, d),
      htmlFlowData: pt,
      htmlText: s(xa, d),
      htmlTextData: pt,
      image: s(Ea),
      label: d,
      link: s(zl),
      listItem: s(gi),
      listItemValue: T,
      listOrdered: s(Tl, v),
      listUnordered: s(Tl),
      paragraph: s(Iu),
      reference: S,
      referenceString: d,
      resourceDestinationString: d,
      resourceTitleString: d,
      setextHeading: s(xl),
      strong: s(Wu),
      thematicBreak: s($u),
    },
    exit: {
      atxHeading: y(),
      atxHeadingSequence: yt,
      autolink: y(),
      autolinkEmail: ut,
      autolinkProtocol: V,
      blockQuote: y(),
      characterEscapeValue: Et,
      characterReferenceMarkerHexadecimal: ct,
      characterReferenceMarkerNumeric: ct,
      characterReferenceValue: at,
      characterReference: zt,
      codeFenced: y(F),
      codeFencedFence: G,
      codeFencedFenceInfo: x,
      codeFencedFenceMeta: X,
      codeFlowValue: Et,
      codeIndented: y(Y),
      codeText: y(Q),
      codeTextData: Et,
      data: Et,
      definition: y(),
      definitionDestinationString: mt,
      definitionLabelString: it,
      definitionTitleString: K,
      emphasis: y(),
      hardBreakEscape: y($),
      hardBreakTrailing: y($),
      htmlFlow: y(_t),
      htmlFlowData: Et,
      htmlText: y(lt),
      htmlTextData: Et,
      image: y(B),
      label: xt,
      labelText: P,
      lineEnding: tt,
      link: y(M),
      listItem: y(),
      listOrdered: y(),
      listUnordered: y(),
      paragraph: y(),
      referenceString: I,
      resourceDestinationString: E,
      resourceTitleString: A,
      resource: U,
      setextHeading: y(ht),
      setextHeadingLineSequence: W,
      setextHeadingText: H,
      strong: y(),
      thematicBreak: y(),
    },
  };
  Sm(u, (i || {}).mdastExtensions || []);
  const r = {};
  return c;
  function c(j) {
    let J = { type: "root", children: [] };
    const ft = {
        stack: [J],
        tokenStack: [],
        config: u,
        enter: m,
        exit: p,
        buffer: d,
        resume: b,
        data: r,
      },
      Tt = [];
    let Bt = -1;
    for (; ++Bt < j.length; )
      if (j[Bt][1].type === "listOrdered" || j[Bt][1].type === "listUnordered")
        if (j[Bt][0] === "enter") Tt.push(Bt);
        else {
          const Me = Tt.pop();
          Bt = f(j, Me, Bt);
        }
    for (Bt = -1; ++Bt < j.length; ) {
      const Me = u[j[Bt][0]];
      vm.call(Me, j[Bt][1].type) &&
        Me[j[Bt][1].type].call(
          Object.assign({ sliceSerialize: j[Bt][2].sliceSerialize }, ft),
          j[Bt][1],
        );
    }
    if (ft.tokenStack.length > 0) {
      const Me = ft.tokenStack[ft.tokenStack.length - 1];
      (Me[1] || Mp).call(ft, void 0, Me[0]);
    }
    for (
      J.position = {
        start: tl(
          j.length > 0 ? j[0][1].start : { line: 1, column: 1, offset: 0 },
        ),
        end: tl(
          j.length > 0
            ? j[j.length - 2][1].end
            : { line: 1, column: 1, offset: 0 },
        ),
      },
        Bt = -1;
      ++Bt < u.transforms.length;
    )
      J = u.transforms[Bt](J) || J;
    return J;
  }
  function f(j, J, ft) {
    let Tt = J - 1,
      Bt = -1,
      Me = !1,
      fn,
      ye,
      ie,
      ve;
    for (; ++Tt <= ft; ) {
      const Gt = j[Tt];
      switch (Gt[1].type) {
        case "listUnordered":
        case "listOrdered":
        case "blockQuote": {
          (Gt[0] === "enter" ? Bt++ : Bt--, (ve = void 0));
          break;
        }
        case "lineEndingBlank": {
          Gt[0] === "enter" &&
            (fn && !ve && !Bt && !ie && (ie = Tt), (ve = void 0));
          break;
        }
        case "linePrefix":
        case "listItemValue":
        case "listItemMarker":
        case "listItemPrefix":
        case "listItemPrefixWhitespace":
          break;
        default:
          ve = void 0;
      }
      if (
        (!Bt && Gt[0] === "enter" && Gt[1].type === "listItemPrefix") ||
        (Bt === -1 &&
          Gt[0] === "exit" &&
          (Gt[1].type === "listUnordered" || Gt[1].type === "listOrdered"))
      ) {
        if (fn) {
          let Dn = Tt;
          for (ye = void 0; Dn--; ) {
            const We = j[Dn];
            if (
              We[1].type === "lineEnding" ||
              We[1].type === "lineEndingBlank"
            ) {
              if (We[0] === "exit") continue;
              (ye && ((j[ye][1].type = "lineEndingBlank"), (Me = !0)),
                (We[1].type = "lineEnding"),
                (ye = Dn));
            } else if (
              !(
                We[1].type === "linePrefix" ||
                We[1].type === "blockQuotePrefix" ||
                We[1].type === "blockQuotePrefixWhitespace" ||
                We[1].type === "blockQuoteMarker" ||
                We[1].type === "listItemIndent"
              )
            )
              break;
          }
          (ie && (!ye || ie < ye) && (fn._spread = !0),
            (fn.end = Object.assign({}, ye ? j[ye][1].start : Gt[1].end)),
            j.splice(ye || Tt, 0, ["exit", fn, Gt[2]]),
            Tt++,
            ft++);
        }
        if (Gt[1].type === "listItemPrefix") {
          const Dn = {
            type: "listItem",
            _spread: !1,
            start: Object.assign({}, Gt[1].start),
            end: void 0,
          };
          ((fn = Dn),
            j.splice(Tt, 0, ["enter", Dn, Gt[2]]),
            Tt++,
            ft++,
            (ie = void 0),
            (ve = !0));
        }
      }
    }
    return ((j[J][1]._spread = Me), ft);
  }
  function s(j, J) {
    return ft;
    function ft(Tt) {
      (m.call(this, j(Tt), Tt), J && J.call(this, Tt));
    }
  }
  function d() {
    this.stack.push({ type: "fragment", children: [] });
  }
  function m(j, J, ft) {
    (this.stack[this.stack.length - 1].children.push(j),
      this.stack.push(j),
      this.tokenStack.push([J, ft || void 0]),
      (j.position = { start: tl(J.start), end: void 0 }));
  }
  function y(j) {
    return J;
    function J(ft) {
      (j && j.call(this, ft), p.call(this, ft));
    }
  }
  function p(j, J) {
    const ft = this.stack.pop(),
      Tt = this.tokenStack.pop();
    if (Tt)
      Tt[0].type !== j.type &&
        (J ? J.call(this, j, Tt[0]) : (Tt[1] || Mp).call(this, j, Tt[0]));
    else
      throw new Error(
        "Cannot close `" +
          j.type +
          "` (" +
          pa({ start: j.start, end: j.end }) +
          "): it’s not open",
      );
    ft.position.end = tl(j.end);
  }
  function b() {
    return I1(this.stack.pop());
  }
  function v() {
    this.data.expectingFirstListItemValue = !0;
  }
  function T(j) {
    if (this.data.expectingFirstListItemValue) {
      const J = this.stack[this.stack.length - 2];
      ((J.start = Number.parseInt(this.sliceSerialize(j), 10)),
        (this.data.expectingFirstListItemValue = void 0));
    }
  }
  function x() {
    const j = this.resume(),
      J = this.stack[this.stack.length - 1];
    J.lang = j;
  }
  function X() {
    const j = this.resume(),
      J = this.stack[this.stack.length - 1];
    J.meta = j;
  }
  function G() {
    this.data.flowCodeInside ||
      (this.buffer(), (this.data.flowCodeInside = !0));
  }
  function F() {
    const j = this.resume(),
      J = this.stack[this.stack.length - 1];
    ((J.value = j.replace(/^(\r?\n|\r)|(\r?\n|\r)$/g, "")),
      (this.data.flowCodeInside = void 0));
  }
  function Y() {
    const j = this.resume(),
      J = this.stack[this.stack.length - 1];
    J.value = j.replace(/(\r?\n|\r)$/g, "");
  }
  function it(j) {
    const J = this.resume(),
      ft = this.stack[this.stack.length - 1];
    ((ft.label = J),
      (ft.identifier = hi(this.sliceSerialize(j)).toLowerCase()));
  }
  function K() {
    const j = this.resume(),
      J = this.stack[this.stack.length - 1];
    J.title = j;
  }
  function mt() {
    const j = this.resume(),
      J = this.stack[this.stack.length - 1];
    J.url = j;
  }
  function yt(j) {
    const J = this.stack[this.stack.length - 1];
    if (!J.depth) {
      const ft = this.sliceSerialize(j).length;
      J.depth = ft;
    }
  }
  function H() {
    this.data.setextHeadingSlurpLineEnding = !0;
  }
  function W(j) {
    const J = this.stack[this.stack.length - 1];
    J.depth = this.sliceSerialize(j).codePointAt(0) === 61 ? 1 : 2;
  }
  function ht() {
    this.data.setextHeadingSlurpLineEnding = void 0;
  }
  function pt(j) {
    const ft = this.stack[this.stack.length - 1].children;
    let Tt = ft[ft.length - 1];
    ((!Tt || Tt.type !== "text") &&
      ((Tt = ge()),
      (Tt.position = { start: tl(j.start), end: void 0 }),
      ft.push(Tt)),
      this.stack.push(Tt));
  }
  function Et(j) {
    const J = this.stack.pop();
    ((J.value += this.sliceSerialize(j)), (J.position.end = tl(j.end)));
  }
  function tt(j) {
    const J = this.stack[this.stack.length - 1];
    if (this.data.atHardBreak) {
      const ft = J.children[J.children.length - 1];
      ((ft.position.end = tl(j.end)), (this.data.atHardBreak = void 0));
      return;
    }
    !this.data.setextHeadingSlurpLineEnding &&
      u.canContainEols.includes(J.type) &&
      (pt.call(this, j), Et.call(this, j));
  }
  function $() {
    this.data.atHardBreak = !0;
  }
  function _t() {
    const j = this.resume(),
      J = this.stack[this.stack.length - 1];
    J.value = j;
  }
  function lt() {
    const j = this.resume(),
      J = this.stack[this.stack.length - 1];
    J.value = j;
  }
  function Q() {
    const j = this.resume(),
      J = this.stack[this.stack.length - 1];
    J.value = j;
  }
  function M() {
    const j = this.stack[this.stack.length - 1];
    if (this.data.inReference) {
      const J = this.data.referenceType || "shortcut";
      ((j.type += "Reference"),
        (j.referenceType = J),
        delete j.url,
        delete j.title);
    } else (delete j.identifier, delete j.label);
    this.data.referenceType = void 0;
  }
  function B() {
    const j = this.stack[this.stack.length - 1];
    if (this.data.inReference) {
      const J = this.data.referenceType || "shortcut";
      ((j.type += "Reference"),
        (j.referenceType = J),
        delete j.url,
        delete j.title);
    } else (delete j.identifier, delete j.label);
    this.data.referenceType = void 0;
  }
  function P(j) {
    const J = this.sliceSerialize(j),
      ft = this.stack[this.stack.length - 2];
    ((ft.label = Fb(J)), (ft.identifier = hi(J).toLowerCase()));
  }
  function xt() {
    const j = this.stack[this.stack.length - 1],
      J = this.resume(),
      ft = this.stack[this.stack.length - 1];
    if (((this.data.inReference = !0), ft.type === "link")) {
      const Tt = j.children;
      ft.children = Tt;
    } else ft.alt = J;
  }
  function E() {
    const j = this.resume(),
      J = this.stack[this.stack.length - 1];
    J.url = j;
  }
  function A() {
    const j = this.resume(),
      J = this.stack[this.stack.length - 1];
    J.title = j;
  }
  function U() {
    this.data.inReference = void 0;
  }
  function S() {
    this.data.referenceType = "collapsed";
  }
  function I(j) {
    const J = this.resume(),
      ft = this.stack[this.stack.length - 1];
    ((ft.label = J),
      (ft.identifier = hi(this.sliceSerialize(j)).toLowerCase()),
      (this.data.referenceType = "full"));
  }
  function ct(j) {
    this.data.characterReferenceType = j.type;
  }
  function at(j) {
    const J = this.sliceSerialize(j),
      ft = this.data.characterReferenceType;
    let Tt;
    ft
      ? ((Tt = om(J, ft === "characterReferenceMarkerNumeric" ? 10 : 16)),
        (this.data.characterReferenceType = void 0))
      : (Tt = Jo(J));
    const Bt = this.stack[this.stack.length - 1];
    Bt.value += Tt;
  }
  function zt(j) {
    const J = this.stack.pop();
    J.position.end = tl(j.end);
  }
  function V(j) {
    Et.call(this, j);
    const J = this.stack[this.stack.length - 1];
    J.url = this.sliceSerialize(j);
  }
  function ut(j) {
    Et.call(this, j);
    const J = this.stack[this.stack.length - 1];
    J.url = "mailto:" + this.sliceSerialize(j);
  }
  function kt() {
    return { type: "blockquote", children: [] };
  }
  function me() {
    return { type: "code", lang: null, meta: null, value: "" };
  }
  function mi() {
    return { type: "inlineCode", value: "" };
  }
  function Sa() {
    return {
      type: "definition",
      identifier: "",
      label: null,
      title: null,
      url: "",
    };
  }
  function on() {
    return { type: "emphasis", children: [] };
  }
  function xl() {
    return { type: "heading", depth: 0, children: [] };
  }
  function El() {
    return { type: "break" };
  }
  function xa() {
    return { type: "html", value: "" };
  }
  function Ea() {
    return { type: "image", title: null, url: "", alt: null };
  }
  function zl() {
    return { type: "link", title: null, url: "", children: [] };
  }
  function Tl(j) {
    return {
      type: "list",
      ordered: j.type === "listOrdered",
      start: null,
      spread: j._spread,
      children: [],
    };
  }
  function gi(j) {
    return { type: "listItem", spread: j._spread, checked: null, children: [] };
  }
  function Iu() {
    return { type: "paragraph", children: [] };
  }
  function Wu() {
    return { type: "strong", children: [] };
  }
  function ge() {
    return { type: "text", value: "" };
  }
  function $u() {
    return { type: "thematicBreak" };
  }
}
function tl(i) {
  return { line: i.line, column: i.column, offset: i.offset };
}
function Sm(i, u) {
  let r = -1;
  for (; ++r < u.length; ) {
    const c = u[r];
    Array.isArray(c) ? Sm(i, c) : Pb(i, c);
  }
}
function Pb(i, u) {
  let r;
  for (r in u)
    if (vm.call(u, r))
      switch (r) {
        case "canContainEols": {
          const c = u[r];
          c && i[r].push(...c);
          break;
        }
        case "transforms": {
          const c = u[r];
          c && i[r].push(...c);
          break;
        }
        case "enter":
        case "exit": {
          const c = u[r];
          c && Object.assign(i[r], c);
          break;
        }
      }
}
function Mp(i, u) {
  throw i
    ? new Error(
        "Cannot close `" +
          i.type +
          "` (" +
          pa({ start: i.start, end: i.end }) +
          "): a different token (`" +
          u.type +
          "`, " +
          pa({ start: u.start, end: u.end }) +
          ") is open",
      )
    : new Error(
        "Cannot close document, a token (`" +
          u.type +
          "`, " +
          pa({ start: u.start, end: u.end }) +
          ") is still open",
      );
}
function tv(i) {
  const u = this;
  u.parser = r;
  function r(c) {
    return Wb(c, {
      ...u.data("settings"),
      ...i,
      extensions: u.data("micromarkExtensions") || [],
      mdastExtensions: u.data("fromMarkdownExtensions") || [],
    });
  }
}
function ev(i, u) {
  const r = {
    type: "element",
    tagName: "blockquote",
    properties: {},
    children: i.wrap(i.all(u), !0),
  };
  return (i.patch(u, r), i.applyData(u, r));
}
function nv(i, u) {
  const r = { type: "element", tagName: "br", properties: {}, children: [] };
  return (
    i.patch(u, r),
    [
      i.applyData(u, r),
      {
        type: "text",
        value: `
`,
      },
    ]
  );
}
function lv(i, u) {
  const r = u.value
      ? u.value +
        `
`
      : "",
    c = {},
    f = u.lang ? u.lang.split(/\s+/) : [];
  f.length > 0 && (c.className = ["language-" + f[0]]);
  let s = {
    type: "element",
    tagName: "code",
    properties: c,
    children: [{ type: "text", value: r }],
  };
  return (
    u.meta && (s.data = { meta: u.meta }),
    i.patch(u, s),
    (s = i.applyData(u, s)),
    (s = { type: "element", tagName: "pre", properties: {}, children: [s] }),
    i.patch(u, s),
    s
  );
}
function iv(i, u) {
  const r = {
    type: "element",
    tagName: "del",
    properties: {},
    children: i.all(u),
  };
  return (i.patch(u, r), i.applyData(u, r));
}
function av(i, u) {
  const r = {
    type: "element",
    tagName: "em",
    properties: {},
    children: i.all(u),
  };
  return (i.patch(u, r), i.applyData(u, r));
}
function uv(i, u) {
  const r =
      typeof i.options.clobberPrefix == "string"
        ? i.options.clobberPrefix
        : "user-content-",
    c = String(u.identifier).toUpperCase(),
    f = pi(c.toLowerCase()),
    s = i.footnoteOrder.indexOf(c);
  let d,
    m = i.footnoteCounts.get(c);
  (m === void 0
    ? ((m = 0), i.footnoteOrder.push(c), (d = i.footnoteOrder.length))
    : (d = s + 1),
    (m += 1),
    i.footnoteCounts.set(c, m));
  const y = {
    type: "element",
    tagName: "a",
    properties: {
      href: "#" + r + "fn-" + f,
      id: r + "fnref-" + f + (m > 1 ? "-" + m : ""),
      dataFootnoteRef: !0,
      ariaDescribedBy: ["footnote-label"],
    },
    children: [{ type: "text", value: String(d) }],
  };
  i.patch(u, y);
  const p = { type: "element", tagName: "sup", properties: {}, children: [y] };
  return (i.patch(u, p), i.applyData(u, p));
}
function rv(i, u) {
  const r = {
    type: "element",
    tagName: "h" + u.depth,
    properties: {},
    children: i.all(u),
  };
  return (i.patch(u, r), i.applyData(u, r));
}
function cv(i, u) {
  if (i.options.allowDangerousHtml) {
    const r = { type: "raw", value: u.value };
    return (i.patch(u, r), i.applyData(u, r));
  }
}
function xm(i, u) {
  const r = u.referenceType;
  let c = "]";
  if (
    (r === "collapsed"
      ? (c += "[]")
      : r === "full" && (c += "[" + (u.label || u.identifier) + "]"),
    u.type === "imageReference")
  )
    return [{ type: "text", value: "![" + u.alt + c }];
  const f = i.all(u),
    s = f[0];
  s && s.type === "text"
    ? (s.value = "[" + s.value)
    : f.unshift({ type: "text", value: "[" });
  const d = f[f.length - 1];
  return (
    d && d.type === "text"
      ? (d.value += c)
      : f.push({ type: "text", value: c }),
    f
  );
}
function ov(i, u) {
  const r = String(u.identifier).toUpperCase(),
    c = i.definitionById.get(r);
  if (!c) return xm(i, u);
  const f = { src: pi(c.url || ""), alt: u.alt };
  c.title !== null && c.title !== void 0 && (f.title = c.title);
  const s = { type: "element", tagName: "img", properties: f, children: [] };
  return (i.patch(u, s), i.applyData(u, s));
}
function fv(i, u) {
  const r = { src: pi(u.url) };
  (u.alt !== null && u.alt !== void 0 && (r.alt = u.alt),
    u.title !== null && u.title !== void 0 && (r.title = u.title));
  const c = { type: "element", tagName: "img", properties: r, children: [] };
  return (i.patch(u, c), i.applyData(u, c));
}
function sv(i, u) {
  const r = { type: "text", value: u.value.replace(/\r?\n|\r/g, " ") };
  i.patch(u, r);
  const c = { type: "element", tagName: "code", properties: {}, children: [r] };
  return (i.patch(u, c), i.applyData(u, c));
}
function hv(i, u) {
  const r = String(u.identifier).toUpperCase(),
    c = i.definitionById.get(r);
  if (!c) return xm(i, u);
  const f = { href: pi(c.url || "") };
  c.title !== null && c.title !== void 0 && (f.title = c.title);
  const s = {
    type: "element",
    tagName: "a",
    properties: f,
    children: i.all(u),
  };
  return (i.patch(u, s), i.applyData(u, s));
}
function dv(i, u) {
  const r = { href: pi(u.url) };
  u.title !== null && u.title !== void 0 && (r.title = u.title);
  const c = {
    type: "element",
    tagName: "a",
    properties: r,
    children: i.all(u),
  };
  return (i.patch(u, c), i.applyData(u, c));
}
function pv(i, u, r) {
  const c = i.all(u),
    f = r ? mv(r) : Em(u),
    s = {},
    d = [];
  if (typeof u.checked == "boolean") {
    const b = c[0];
    let v;
    (b && b.type === "element" && b.tagName === "p"
      ? (v = b)
      : ((v = { type: "element", tagName: "p", properties: {}, children: [] }),
        c.unshift(v)),
      v.children.length > 0 && v.children.unshift({ type: "text", value: " " }),
      v.children.unshift({
        type: "element",
        tagName: "input",
        properties: { type: "checkbox", checked: u.checked, disabled: !0 },
        children: [],
      }),
      (s.className = ["task-list-item"]));
  }
  let m = -1;
  for (; ++m < c.length; ) {
    const b = c[m];
    ((f || m !== 0 || b.type !== "element" || b.tagName !== "p") &&
      d.push({
        type: "text",
        value: `
`,
      }),
      b.type === "element" && b.tagName === "p" && !f
        ? d.push(...b.children)
        : d.push(b));
  }
  const y = c[c.length - 1];
  y &&
    (f || y.type !== "element" || y.tagName !== "p") &&
    d.push({
      type: "text",
      value: `
`,
    });
  const p = { type: "element", tagName: "li", properties: s, children: d };
  return (i.patch(u, p), i.applyData(u, p));
}
function mv(i) {
  let u = !1;
  if (i.type === "list") {
    u = i.spread || !1;
    const r = i.children;
    let c = -1;
    for (; !u && ++c < r.length; ) u = Em(r[c]);
  }
  return u;
}
function Em(i) {
  const u = i.spread;
  return u ?? i.children.length > 1;
}
function gv(i, u) {
  const r = {},
    c = i.all(u);
  let f = -1;
  for (
    typeof u.start == "number" && u.start !== 1 && (r.start = u.start);
    ++f < c.length;
  ) {
    const d = c[f];
    if (
      d.type === "element" &&
      d.tagName === "li" &&
      d.properties &&
      Array.isArray(d.properties.className) &&
      d.properties.className.includes("task-list-item")
    ) {
      r.className = ["contains-task-list"];
      break;
    }
  }
  const s = {
    type: "element",
    tagName: u.ordered ? "ol" : "ul",
    properties: r,
    children: i.wrap(c, !0),
  };
  return (i.patch(u, s), i.applyData(u, s));
}
function yv(i, u) {
  const r = {
    type: "element",
    tagName: "p",
    properties: {},
    children: i.all(u),
  };
  return (i.patch(u, r), i.applyData(u, r));
}
function bv(i, u) {
  const r = { type: "root", children: i.wrap(i.all(u)) };
  return (i.patch(u, r), i.applyData(u, r));
}
function vv(i, u) {
  const r = {
    type: "element",
    tagName: "strong",
    properties: {},
    children: i.all(u),
  };
  return (i.patch(u, r), i.applyData(u, r));
}
function Sv(i, u) {
  const r = i.all(u),
    c = r.shift(),
    f = [];
  if (c) {
    const d = {
      type: "element",
      tagName: "thead",
      properties: {},
      children: i.wrap([c], !0),
    };
    (i.patch(u.children[0], d), f.push(d));
  }
  if (r.length > 0) {
    const d = {
        type: "element",
        tagName: "tbody",
        properties: {},
        children: i.wrap(r, !0),
      },
      m = Qo(u.children[1]),
      y = nm(u.children[u.children.length - 1]);
    (m && y && (d.position = { start: m, end: y }), f.push(d));
  }
  const s = {
    type: "element",
    tagName: "table",
    properties: {},
    children: i.wrap(f, !0),
  };
  return (i.patch(u, s), i.applyData(u, s));
}
function xv(i, u, r) {
  const c = r ? r.children : void 0,
    s = (c ? c.indexOf(u) : 1) === 0 ? "th" : "td",
    d = r && r.type === "table" ? r.align : void 0,
    m = d ? d.length : u.children.length;
  let y = -1;
  const p = [];
  for (; ++y < m; ) {
    const v = u.children[y],
      T = {},
      x = d ? d[y] : void 0;
    x && (T.align = x);
    let X = { type: "element", tagName: s, properties: T, children: [] };
    (v && ((X.children = i.all(v)), i.patch(v, X), (X = i.applyData(v, X))),
      p.push(X));
  }
  const b = {
    type: "element",
    tagName: "tr",
    properties: {},
    children: i.wrap(p, !0),
  };
  return (i.patch(u, b), i.applyData(u, b));
}
function Ev(i, u) {
  const r = {
    type: "element",
    tagName: "td",
    properties: {},
    children: i.all(u),
  };
  return (i.patch(u, r), i.applyData(u, r));
}
const kp = 9,
  wp = 32;
function zv(i) {
  const u = String(i),
    r = /\r?\n|\r/g;
  let c = r.exec(u),
    f = 0;
  const s = [];
  for (; c; )
    (s.push(Np(u.slice(f, c.index), f > 0, !0), c[0]),
      (f = c.index + c[0].length),
      (c = r.exec(u)));
  return (s.push(Np(u.slice(f), f > 0, !1)), s.join(""));
}
function Np(i, u, r) {
  let c = 0,
    f = i.length;
  if (u) {
    let s = i.codePointAt(c);
    for (; s === kp || s === wp; ) (c++, (s = i.codePointAt(c)));
  }
  if (r) {
    let s = i.codePointAt(f - 1);
    for (; s === kp || s === wp; ) (f--, (s = i.codePointAt(f - 1)));
  }
  return f > c ? i.slice(c, f) : "";
}
function Tv(i, u) {
  const r = { type: "text", value: zv(String(u.value)) };
  return (i.patch(u, r), i.applyData(u, r));
}
function Av(i, u) {
  const r = { type: "element", tagName: "hr", properties: {}, children: [] };
  return (i.patch(u, r), i.applyData(u, r));
}
const Cv = {
  blockquote: ev,
  break: nv,
  code: lv,
  delete: iv,
  emphasis: av,
  footnoteReference: uv,
  heading: rv,
  html: cv,
  imageReference: ov,
  image: fv,
  inlineCode: sv,
  linkReference: hv,
  link: dv,
  listItem: pv,
  list: gv,
  paragraph: yv,
  root: bv,
  strong: vv,
  table: Sv,
  tableCell: Ev,
  tableRow: xv,
  text: Tv,
  thematicBreak: Av,
  toml: Lu,
  yaml: Lu,
  definition: Lu,
  footnoteDefinition: Lu,
};
function Lu() {}
const zm = -1,
  Ku = 0,
  ga = 1,
  Qu = 2,
  Wo = 3,
  $o = 4,
  Po = 5,
  tf = 6,
  Tm = 7,
  Am = 8,
  Rp = typeof self == "object" ? self : globalThis,
  _v = (i, u) => {
    const r = (f, s) => (i.set(s, f), f),
      c = (f) => {
        if (i.has(f)) return i.get(f);
        const [s, d] = u[f];
        switch (s) {
          case Ku:
          case zm:
            return r(d, f);
          case ga: {
            const m = r([], f);
            for (const y of d) m.push(c(y));
            return m;
          }
          case Qu: {
            const m = r({}, f);
            for (const [y, p] of d) m[c(y)] = c(p);
            return m;
          }
          case Wo:
            return r(new Date(d), f);
          case $o: {
            const { source: m, flags: y } = d;
            return r(new RegExp(m, y), f);
          }
          case Po: {
            const m = r(new Map(), f);
            for (const [y, p] of d) m.set(c(y), c(p));
            return m;
          }
          case tf: {
            const m = r(new Set(), f);
            for (const y of d) m.add(c(y));
            return m;
          }
          case Tm: {
            const { name: m, message: y } = d;
            return r(new Rp[m](y), f);
          }
          case Am:
            return r(BigInt(d), f);
          case "BigInt":
            return r(Object(BigInt(d)), f);
          case "ArrayBuffer":
            return r(new Uint8Array(d).buffer, d);
          case "DataView": {
            const { buffer: m } = new Uint8Array(d);
            return r(new DataView(m), d);
          }
        }
        return r(new Rp[s](d), f);
      };
    return c;
  },
  Up = (i) => _v(new Map(), i)(0),
  fi = "",
  { toString: Ov } = {},
  { keys: Dv } = Object,
  da = (i) => {
    const u = typeof i;
    if (u !== "object" || !i) return [Ku, u];
    const r = Ov.call(i).slice(8, -1);
    switch (r) {
      case "Array":
        return [ga, fi];
      case "Object":
        return [Qu, fi];
      case "Date":
        return [Wo, fi];
      case "RegExp":
        return [$o, fi];
      case "Map":
        return [Po, fi];
      case "Set":
        return [tf, fi];
      case "DataView":
        return [ga, r];
    }
    return r.includes("Array")
      ? [ga, r]
      : r.includes("Error")
        ? [Tm, r]
        : [Qu, r];
  },
  qu = ([i, u]) => i === Ku && (u === "function" || u === "symbol"),
  Mv = (i, u, r, c) => {
    const f = (d, m) => {
        const y = c.push(d) - 1;
        return (r.set(m, y), y);
      },
      s = (d) => {
        if (r.has(d)) return r.get(d);
        let [m, y] = da(d);
        switch (m) {
          case Ku: {
            let b = d;
            switch (y) {
              case "bigint":
                ((m = Am), (b = d.toString()));
                break;
              case "function":
              case "symbol":
                if (i) throw new TypeError("unable to serialize " + y);
                b = null;
                break;
              case "undefined":
                return f([zm], d);
            }
            return f([m, b], d);
          }
          case ga: {
            if (y) {
              let T = d;
              return (
                y === "DataView"
                  ? (T = new Uint8Array(d.buffer))
                  : y === "ArrayBuffer" && (T = new Uint8Array(d)),
                f([y, [...T]], d)
              );
            }
            const b = [],
              v = f([m, b], d);
            for (const T of d) b.push(s(T));
            return v;
          }
          case Qu: {
            if (y)
              switch (y) {
                case "BigInt":
                  return f([y, d.toString()], d);
                case "Boolean":
                case "Number":
                case "String":
                  return f([y, d.valueOf()], d);
              }
            if (u && "toJSON" in d) return s(d.toJSON());
            const b = [],
              v = f([m, b], d);
            for (const T of Dv(d))
              (i || !qu(da(d[T]))) && b.push([s(T), s(d[T])]);
            return v;
          }
          case Wo:
            return f([m, d.toISOString()], d);
          case $o: {
            const { source: b, flags: v } = d;
            return f([m, { source: b, flags: v }], d);
          }
          case Po: {
            const b = [],
              v = f([m, b], d);
            for (const [T, x] of d)
              (i || !(qu(da(T)) || qu(da(x)))) && b.push([s(T), s(x)]);
            return v;
          }
          case tf: {
            const b = [],
              v = f([m, b], d);
            for (const T of d) (i || !qu(da(T))) && b.push(s(T));
            return v;
          }
        }
        const { message: p } = d;
        return f([m, { name: y, message: p }], d);
      };
    return s;
  },
  Bp = (i, { json: u, lossy: r } = {}) => {
    const c = [];
    return (Mv(!(u || r), !!u, new Map(), c)(i), c);
  },
  Vu =
    typeof structuredClone == "function"
      ? (i, u) =>
          u && ("json" in u || "lossy" in u) ? Up(Bp(i, u)) : structuredClone(i)
      : (i, u) => Up(Bp(i, u));
function kv(i, u) {
  const r = [{ type: "text", value: "↩" }];
  return (
    u > 1 &&
      r.push({
        type: "element",
        tagName: "sup",
        properties: {},
        children: [{ type: "text", value: String(u) }],
      }),
    r
  );
}
function wv(i, u) {
  return "Back to reference " + (i + 1) + (u > 1 ? "-" + u : "");
}
function Nv(i) {
  const u =
      typeof i.options.clobberPrefix == "string"
        ? i.options.clobberPrefix
        : "user-content-",
    r = i.options.footnoteBackContent || kv,
    c = i.options.footnoteBackLabel || wv,
    f = i.options.footnoteLabel || "Footnotes",
    s = i.options.footnoteLabelTagName || "h2",
    d = i.options.footnoteLabelProperties || { className: ["sr-only"] },
    m = [];
  let y = -1;
  for (; ++y < i.footnoteOrder.length; ) {
    const p = i.footnoteById.get(i.footnoteOrder[y]);
    if (!p) continue;
    const b = i.all(p),
      v = String(p.identifier).toUpperCase(),
      T = pi(v.toLowerCase());
    let x = 0;
    const X = [],
      G = i.footnoteCounts.get(v);
    for (; G !== void 0 && ++x <= G; ) {
      X.length > 0 && X.push({ type: "text", value: " " });
      let it = typeof r == "string" ? r : r(y, x);
      (typeof it == "string" && (it = { type: "text", value: it }),
        X.push({
          type: "element",
          tagName: "a",
          properties: {
            href: "#" + u + "fnref-" + T + (x > 1 ? "-" + x : ""),
            dataFootnoteBackref: "",
            ariaLabel: typeof c == "string" ? c : c(y, x),
            className: ["data-footnote-backref"],
          },
          children: Array.isArray(it) ? it : [it],
        }));
    }
    const F = b[b.length - 1];
    if (F && F.type === "element" && F.tagName === "p") {
      const it = F.children[F.children.length - 1];
      (it && it.type === "text"
        ? (it.value += " ")
        : F.children.push({ type: "text", value: " " }),
        F.children.push(...X));
    } else b.push(...X);
    const Y = {
      type: "element",
      tagName: "li",
      properties: { id: u + "fn-" + T },
      children: i.wrap(b, !0),
    };
    (i.patch(p, Y), m.push(Y));
  }
  if (m.length !== 0)
    return {
      type: "element",
      tagName: "section",
      properties: { dataFootnotes: !0, className: ["footnotes"] },
      children: [
        {
          type: "element",
          tagName: s,
          properties: { ...Vu(d), id: "footnote-label" },
          children: [{ type: "text", value: f }],
        },
        {
          type: "text",
          value: `
`,
        },
        {
          type: "element",
          tagName: "ol",
          properties: {},
          children: i.wrap(m, !0),
        },
        {
          type: "text",
          value: `
`,
        },
      ],
    };
}
const Cm = function (i) {
  if (i == null) return jv;
  if (typeof i == "function") return Ju(i);
  if (typeof i == "object") return Array.isArray(i) ? Rv(i) : Uv(i);
  if (typeof i == "string") return Bv(i);
  throw new Error("Expected function, string, or object as test");
};
function Rv(i) {
  const u = [];
  let r = -1;
  for (; ++r < i.length; ) u[r] = Cm(i[r]);
  return Ju(c);
  function c(...f) {
    let s = -1;
    for (; ++s < u.length; ) if (u[s].apply(this, f)) return !0;
    return !1;
  }
}
function Uv(i) {
  const u = i;
  return Ju(r);
  function r(c) {
    const f = c;
    let s;
    for (s in i) if (f[s] !== u[s]) return !1;
    return !0;
  }
}
function Bv(i) {
  return Ju(u);
  function u(r) {
    return r && r.type === i;
  }
}
function Ju(i) {
  return u;
  function u(r, c, f) {
    return !!(
      Hv(r) && i.call(this, r, typeof c == "number" ? c : void 0, f || void 0)
    );
  }
}
function jv() {
  return !0;
}
function Hv(i) {
  return i !== null && typeof i == "object" && "type" in i;
}
const _m = [],
  Lv = !0,
  jp = !1,
  qv = "skip";
function Yv(i, u, r, c) {
  let f;
  typeof u == "function" && typeof r != "function"
    ? ((c = r), (r = u))
    : (f = u);
  const s = Cm(f),
    d = c ? -1 : 1;
  m(i, void 0, [])();
  function m(y, p, b) {
    const v = y && typeof y == "object" ? y : {};
    if (typeof v.type == "string") {
      const x =
        typeof v.tagName == "string"
          ? v.tagName
          : typeof v.name == "string"
            ? v.name
            : void 0;
      Object.defineProperty(T, "name", {
        value: "node (" + (y.type + (x ? "<" + x + ">" : "")) + ")",
      });
    }
    return T;
    function T() {
      let x = _m,
        X,
        G,
        F;
      if (
        (!u || s(y, p, b[b.length - 1] || void 0)) &&
        ((x = Gv(r(y, b))), x[0] === jp)
      )
        return x;
      if ("children" in y && y.children) {
        const Y = y;
        if (Y.children && x[0] !== qv)
          for (
            G = (c ? Y.children.length : -1) + d, F = b.concat(Y);
            G > -1 && G < Y.children.length;
          ) {
            const it = Y.children[G];
            if (((X = m(it, G, F)()), X[0] === jp)) return X;
            G = typeof X[1] == "number" ? X[1] : G + d;
          }
      }
      return x;
    }
  }
}
function Gv(i) {
  return Array.isArray(i)
    ? i
    : typeof i == "number"
      ? [Lv, i]
      : i == null
        ? _m
        : [i];
}
function Om(i, u, r, c) {
  let f, s, d;
  (typeof u == "function" && typeof r != "function"
    ? ((s = void 0), (d = u), (f = r))
    : ((s = u), (d = r), (f = c)),
    Yv(i, s, m, f));
  function m(y, p) {
    const b = p[p.length - 1],
      v = b ? b.children.indexOf(y) : void 0;
    return d(y, v, b);
  }
}
const Ho = {}.hasOwnProperty,
  Xv = {};
function Qv(i, u) {
  const r = u || Xv,
    c = new Map(),
    f = new Map(),
    s = new Map(),
    d = { ...Cv, ...r.handlers },
    m = {
      all: p,
      applyData: Zv,
      definitionById: c,
      footnoteById: f,
      footnoteCounts: s,
      footnoteOrder: [],
      handlers: d,
      one: y,
      options: r,
      patch: Vv,
      wrap: Jv,
    };
  return (
    Om(i, function (b) {
      if (b.type === "definition" || b.type === "footnoteDefinition") {
        const v = b.type === "definition" ? c : f,
          T = String(b.identifier).toUpperCase();
        v.has(T) || v.set(T, b);
      }
    }),
    m
  );
  function y(b, v) {
    const T = b.type,
      x = m.handlers[T];
    if (Ho.call(m.handlers, T) && x) return x(m, b, v);
    if (m.options.passThrough && m.options.passThrough.includes(T)) {
      if ("children" in b) {
        const { children: G, ...F } = b,
          Y = Vu(F);
        return ((Y.children = m.all(b)), Y);
      }
      return Vu(b);
    }
    return (m.options.unknownHandler || Kv)(m, b, v);
  }
  function p(b) {
    const v = [];
    if ("children" in b) {
      const T = b.children;
      let x = -1;
      for (; ++x < T.length; ) {
        const X = m.one(T[x], b);
        if (X) {
          if (
            x &&
            T[x - 1].type === "break" &&
            (!Array.isArray(X) && X.type === "text" && (X.value = Hp(X.value)),
            !Array.isArray(X) && X.type === "element")
          ) {
            const G = X.children[0];
            G && G.type === "text" && (G.value = Hp(G.value));
          }
          Array.isArray(X) ? v.push(...X) : v.push(X);
        }
      }
    }
    return v;
  }
}
function Vv(i, u) {
  i.position && (u.position = O1(i));
}
function Zv(i, u) {
  let r = u;
  if (i && i.data) {
    const c = i.data.hName,
      f = i.data.hChildren,
      s = i.data.hProperties;
    if (typeof c == "string")
      if (r.type === "element") r.tagName = c;
      else {
        const d = "children" in r ? r.children : [r];
        r = { type: "element", tagName: c, properties: {}, children: d };
      }
    (r.type === "element" && s && Object.assign(r.properties, Vu(s)),
      "children" in r &&
        r.children &&
        f !== null &&
        f !== void 0 &&
        (r.children = f));
  }
  return r;
}
function Kv(i, u) {
  const r = u.data || {},
    c =
      "value" in u && !(Ho.call(r, "hProperties") || Ho.call(r, "hChildren"))
        ? { type: "text", value: u.value }
        : {
            type: "element",
            tagName: "div",
            properties: {},
            children: i.all(u),
          };
  return (i.patch(u, c), i.applyData(u, c));
}
function Jv(i, u) {
  const r = [];
  let c = -1;
  for (
    u &&
    r.push({
      type: "text",
      value: `
`,
    });
    ++c < i.length;
  )
    (c &&
      r.push({
        type: "text",
        value: `
`,
      }),
      r.push(i[c]));
  return (
    u &&
      i.length > 0 &&
      r.push({
        type: "text",
        value: `
`,
      }),
    r
  );
}
function Hp(i) {
  let u = 0,
    r = i.charCodeAt(u);
  for (; r === 9 || r === 32; ) (u++, (r = i.charCodeAt(u)));
  return i.slice(u);
}
function Lp(i, u) {
  const r = Qv(i, u),
    c = r.one(i, void 0),
    f = Nv(r),
    s = Array.isArray(c)
      ? { type: "root", children: c }
      : c || { type: "root", children: [] };
  return (
    f &&
      s.children.push(
        {
          type: "text",
          value: `
`,
        },
        f,
      ),
    s
  );
}
function Fv(i, u) {
  return i && "run" in i
    ? async function (r, c) {
        const f = Lp(r, { file: c, ...u });
        await i.run(f, c);
      }
    : function (r, c) {
        return Lp(r, { file: c, ...(i || u) });
      };
}
function qp(i) {
  if (i) throw i;
}
var zo, Yp;
function Iv() {
  if (Yp) return zo;
  Yp = 1;
  var i = Object.prototype.hasOwnProperty,
    u = Object.prototype.toString,
    r = Object.defineProperty,
    c = Object.getOwnPropertyDescriptor,
    f = function (p) {
      return typeof Array.isArray == "function"
        ? Array.isArray(p)
        : u.call(p) === "[object Array]";
    },
    s = function (p) {
      if (!p || u.call(p) !== "[object Object]") return !1;
      var b = i.call(p, "constructor"),
        v =
          p.constructor &&
          p.constructor.prototype &&
          i.call(p.constructor.prototype, "isPrototypeOf");
      if (p.constructor && !b && !v) return !1;
      var T;
      for (T in p);
      return typeof T > "u" || i.call(p, T);
    },
    d = function (p, b) {
      r && b.name === "__proto__"
        ? r(p, b.name, {
            enumerable: !0,
            configurable: !0,
            value: b.newValue,
            writable: !0,
          })
        : (p[b.name] = b.newValue);
    },
    m = function (p, b) {
      if (b === "__proto__")
        if (i.call(p, b)) {
          if (c) return c(p, b).value;
        } else return;
      return p[b];
    };
  return (
    (zo = function y() {
      var p,
        b,
        v,
        T,
        x,
        X,
        G = arguments[0],
        F = 1,
        Y = arguments.length,
        it = !1;
      for (
        typeof G == "boolean" && ((it = G), (G = arguments[1] || {}), (F = 2)),
          (G == null || (typeof G != "object" && typeof G != "function")) &&
            (G = {});
        F < Y;
        ++F
      )
        if (((p = arguments[F]), p != null))
          for (b in p)
            ((v = m(G, b)),
              (T = m(p, b)),
              G !== T &&
                (it && T && (s(T) || (x = f(T)))
                  ? (x
                      ? ((x = !1), (X = v && f(v) ? v : []))
                      : (X = v && s(v) ? v : {}),
                    d(G, { name: b, newValue: y(it, X, T) }))
                  : typeof T < "u" && d(G, { name: b, newValue: T })));
      return G;
    }),
    zo
  );
}
var Wv = Iv();
const To = Jp(Wv);
function Lo(i) {
  if (typeof i != "object" || i === null) return !1;
  const u = Object.getPrototypeOf(i);
  return (
    (u === null ||
      u === Object.prototype ||
      Object.getPrototypeOf(u) === null) &&
    !(Symbol.toStringTag in i) &&
    !(Symbol.iterator in i)
  );
}
function $v() {
  const i = [],
    u = { run: r, use: c };
  return u;
  function r(...f) {
    let s = -1;
    const d = f.pop();
    if (typeof d != "function")
      throw new TypeError("Expected function as last argument, not " + d);
    m(null, ...f);
    function m(y, ...p) {
      const b = i[++s];
      let v = -1;
      if (y) {
        d(y);
        return;
      }
      for (; ++v < f.length; )
        (p[v] === null || p[v] === void 0) && (p[v] = f[v]);
      ((f = p), b ? Pv(b, m)(...p) : d(null, ...p));
    }
  }
  function c(f) {
    if (typeof f != "function")
      throw new TypeError("Expected `middelware` to be a function, not " + f);
    return (i.push(f), u);
  }
}
function Pv(i, u) {
  let r;
  return c;
  function c(...d) {
    const m = i.length > d.length;
    let y;
    m && d.push(f);
    try {
      y = i.apply(this, d);
    } catch (p) {
      const b = p;
      if (m && r) throw b;
      return f(b);
    }
    m ||
      (y && y.then && typeof y.then == "function"
        ? y.then(s, f)
        : y instanceof Error
          ? f(y)
          : s(y));
  }
  function f(d, ...m) {
    r || ((r = !0), u(d, ...m));
  }
  function s(d) {
    f(null, d);
  }
}
const un = { basename: tS, dirname: eS, extname: nS, join: lS, sep: "/" };
function tS(i, u) {
  if (u !== void 0 && typeof u != "string")
    throw new TypeError('"ext" argument must be a string');
  va(i);
  let r = 0,
    c = -1,
    f = i.length,
    s;
  if (u === void 0 || u.length === 0 || u.length > i.length) {
    for (; f--; )
      if (i.codePointAt(f) === 47) {
        if (s) {
          r = f + 1;
          break;
        }
      } else c < 0 && ((s = !0), (c = f + 1));
    return c < 0 ? "" : i.slice(r, c);
  }
  if (u === i) return "";
  let d = -1,
    m = u.length - 1;
  for (; f--; )
    if (i.codePointAt(f) === 47) {
      if (s) {
        r = f + 1;
        break;
      }
    } else
      (d < 0 && ((s = !0), (d = f + 1)),
        m > -1 &&
          (i.codePointAt(f) === u.codePointAt(m--)
            ? m < 0 && (c = f)
            : ((m = -1), (c = d))));
  return (r === c ? (c = d) : c < 0 && (c = i.length), i.slice(r, c));
}
function eS(i) {
  if ((va(i), i.length === 0)) return ".";
  let u = -1,
    r = i.length,
    c;
  for (; --r; )
    if (i.codePointAt(r) === 47) {
      if (c) {
        u = r;
        break;
      }
    } else c || (c = !0);
  return u < 0
    ? i.codePointAt(0) === 47
      ? "/"
      : "."
    : u === 1 && i.codePointAt(0) === 47
      ? "//"
      : i.slice(0, u);
}
function nS(i) {
  va(i);
  let u = i.length,
    r = -1,
    c = 0,
    f = -1,
    s = 0,
    d;
  for (; u--; ) {
    const m = i.codePointAt(u);
    if (m === 47) {
      if (d) {
        c = u + 1;
        break;
      }
      continue;
    }
    (r < 0 && ((d = !0), (r = u + 1)),
      m === 46 ? (f < 0 ? (f = u) : s !== 1 && (s = 1)) : f > -1 && (s = -1));
  }
  return f < 0 || r < 0 || s === 0 || (s === 1 && f === r - 1 && f === c + 1)
    ? ""
    : i.slice(f, r);
}
function lS(...i) {
  let u = -1,
    r;
  for (; ++u < i.length; )
    (va(i[u]), i[u] && (r = r === void 0 ? i[u] : r + "/" + i[u]));
  return r === void 0 ? "." : iS(r);
}
function iS(i) {
  va(i);
  const u = i.codePointAt(0) === 47;
  let r = aS(i, !u);
  return (
    r.length === 0 && !u && (r = "."),
    r.length > 0 && i.codePointAt(i.length - 1) === 47 && (r += "/"),
    u ? "/" + r : r
  );
}
function aS(i, u) {
  let r = "",
    c = 0,
    f = -1,
    s = 0,
    d = -1,
    m,
    y;
  for (; ++d <= i.length; ) {
    if (d < i.length) m = i.codePointAt(d);
    else {
      if (m === 47) break;
      m = 47;
    }
    if (m === 47) {
      if (!(f === d - 1 || s === 1))
        if (f !== d - 1 && s === 2) {
          if (
            r.length < 2 ||
            c !== 2 ||
            r.codePointAt(r.length - 1) !== 46 ||
            r.codePointAt(r.length - 2) !== 46
          ) {
            if (r.length > 2) {
              if (((y = r.lastIndexOf("/")), y !== r.length - 1)) {
                (y < 0
                  ? ((r = ""), (c = 0))
                  : ((r = r.slice(0, y)),
                    (c = r.length - 1 - r.lastIndexOf("/"))),
                  (f = d),
                  (s = 0));
                continue;
              }
            } else if (r.length > 0) {
              ((r = ""), (c = 0), (f = d), (s = 0));
              continue;
            }
          }
          u && ((r = r.length > 0 ? r + "/.." : ".."), (c = 2));
        } else
          (r.length > 0
            ? (r += "/" + i.slice(f + 1, d))
            : (r = i.slice(f + 1, d)),
            (c = d - f - 1));
      ((f = d), (s = 0));
    } else m === 46 && s > -1 ? s++ : (s = -1);
  }
  return r;
}
function va(i) {
  if (typeof i != "string")
    throw new TypeError("Path must be a string. Received " + JSON.stringify(i));
}
const uS = { cwd: rS };
function rS() {
  return "/";
}
function qo(i) {
  return !!(
    i !== null &&
    typeof i == "object" &&
    "href" in i &&
    i.href &&
    "protocol" in i &&
    i.protocol &&
    i.auth === void 0
  );
}
function cS(i) {
  if (typeof i == "string") i = new URL(i);
  else if (!qo(i)) {
    const u = new TypeError(
      'The "path" argument must be of type string or an instance of URL. Received `' +
        i +
        "`",
    );
    throw ((u.code = "ERR_INVALID_ARG_TYPE"), u);
  }
  if (i.protocol !== "file:") {
    const u = new TypeError("The URL must be of scheme file");
    throw ((u.code = "ERR_INVALID_URL_SCHEME"), u);
  }
  return oS(i);
}
function oS(i) {
  if (i.hostname !== "") {
    const c = new TypeError(
      'File URL host must be "localhost" or empty on darwin',
    );
    throw ((c.code = "ERR_INVALID_FILE_URL_HOST"), c);
  }
  const u = i.pathname;
  let r = -1;
  for (; ++r < u.length; )
    if (u.codePointAt(r) === 37 && u.codePointAt(r + 1) === 50) {
      const c = u.codePointAt(r + 2);
      if (c === 70 || c === 102) {
        const f = new TypeError(
          "File URL path must not include encoded / characters",
        );
        throw ((f.code = "ERR_INVALID_FILE_URL_PATH"), f);
      }
    }
  return decodeURIComponent(u);
}
const Ao = ["history", "path", "basename", "stem", "extname", "dirname"];
class Dm {
  constructor(u) {
    let r;
    (u
      ? qo(u)
        ? (r = { path: u })
        : typeof u == "string" || fS(u)
          ? (r = { value: u })
          : (r = u)
      : (r = {}),
      (this.cwd = "cwd" in r ? "" : uS.cwd()),
      (this.data = {}),
      (this.history = []),
      (this.messages = []),
      this.value,
      this.map,
      this.result,
      this.stored);
    let c = -1;
    for (; ++c < Ao.length; ) {
      const s = Ao[c];
      s in r &&
        r[s] !== void 0 &&
        r[s] !== null &&
        (this[s] = s === "history" ? [...r[s]] : r[s]);
    }
    let f;
    for (f in r) Ao.includes(f) || (this[f] = r[f]);
  }
  get basename() {
    return typeof this.path == "string" ? un.basename(this.path) : void 0;
  }
  set basename(u) {
    (_o(u, "basename"),
      Co(u, "basename"),
      (this.path = un.join(this.dirname || "", u)));
  }
  get dirname() {
    return typeof this.path == "string" ? un.dirname(this.path) : void 0;
  }
  set dirname(u) {
    (Gp(this.basename, "dirname"),
      (this.path = un.join(u || "", this.basename)));
  }
  get extname() {
    return typeof this.path == "string" ? un.extname(this.path) : void 0;
  }
  set extname(u) {
    if ((Co(u, "extname"), Gp(this.dirname, "extname"), u)) {
      if (u.codePointAt(0) !== 46)
        throw new Error("`extname` must start with `.`");
      if (u.includes(".", 1))
        throw new Error("`extname` cannot contain multiple dots");
    }
    this.path = un.join(this.dirname, this.stem + (u || ""));
  }
  get path() {
    return this.history[this.history.length - 1];
  }
  set path(u) {
    (qo(u) && (u = cS(u)),
      _o(u, "path"),
      this.path !== u && this.history.push(u));
  }
  get stem() {
    return typeof this.path == "string"
      ? un.basename(this.path, this.extname)
      : void 0;
  }
  set stem(u) {
    (_o(u, "stem"),
      Co(u, "stem"),
      (this.path = un.join(this.dirname || "", u + (this.extname || ""))));
  }
  fail(u, r, c) {
    const f = this.message(u, r, c);
    throw ((f.fatal = !0), f);
  }
  info(u, r, c) {
    const f = this.message(u, r, c);
    return ((f.fatal = void 0), f);
  }
  message(u, r, c) {
    const f = new pe(u, r, c);
    return (
      this.path && ((f.name = this.path + ":" + f.name), (f.file = this.path)),
      (f.fatal = !1),
      this.messages.push(f),
      f
    );
  }
  toString(u) {
    return this.value === void 0
      ? ""
      : typeof this.value == "string"
        ? this.value
        : new TextDecoder(u || void 0).decode(this.value);
  }
}
function Co(i, u) {
  if (i && i.includes(un.sep))
    throw new Error(
      "`" + u + "` cannot be a path: did not expect `" + un.sep + "`",
    );
}
function _o(i, u) {
  if (!i) throw new Error("`" + u + "` cannot be empty");
}
function Gp(i, u) {
  if (!i) throw new Error("Setting `" + u + "` requires `path` to be set too");
}
function fS(i) {
  return !!(
    i &&
    typeof i == "object" &&
    "byteLength" in i &&
    "byteOffset" in i
  );
}
const sS = function (i) {
    const c = this.constructor.prototype,
      f = c[i],
      s = function () {
        return f.apply(s, arguments);
      };
    return (Object.setPrototypeOf(s, c), s);
  },
  hS = {}.hasOwnProperty;
class ef extends sS {
  constructor() {
    (super("copy"),
      (this.Compiler = void 0),
      (this.Parser = void 0),
      (this.attachers = []),
      (this.compiler = void 0),
      (this.freezeIndex = -1),
      (this.frozen = void 0),
      (this.namespace = {}),
      (this.parser = void 0),
      (this.transformers = $v()));
  }
  copy() {
    const u = new ef();
    let r = -1;
    for (; ++r < this.attachers.length; ) {
      const c = this.attachers[r];
      u.use(...c);
    }
    return (u.data(To(!0, {}, this.namespace)), u);
  }
  data(u, r) {
    return typeof u == "string"
      ? arguments.length === 2
        ? (Mo("data", this.frozen), (this.namespace[u] = r), this)
        : (hS.call(this.namespace, u) && this.namespace[u]) || void 0
      : u
        ? (Mo("data", this.frozen), (this.namespace = u), this)
        : this.namespace;
  }
  freeze() {
    if (this.frozen) return this;
    const u = this;
    for (; ++this.freezeIndex < this.attachers.length; ) {
      const [r, ...c] = this.attachers[this.freezeIndex];
      if (c[0] === !1) continue;
      c[0] === !0 && (c[0] = void 0);
      const f = r.call(u, ...c);
      typeof f == "function" && this.transformers.use(f);
    }
    return (
      (this.frozen = !0),
      (this.freezeIndex = Number.POSITIVE_INFINITY),
      this
    );
  }
  parse(u) {
    this.freeze();
    const r = Yu(u),
      c = this.parser || this.Parser;
    return (Oo("parse", c), c(String(r), r));
  }
  process(u, r) {
    const c = this;
    return (
      this.freeze(),
      Oo("process", this.parser || this.Parser),
      Do("process", this.compiler || this.Compiler),
      r ? f(void 0, r) : new Promise(f)
    );
    function f(s, d) {
      const m = Yu(u),
        y = c.parse(m);
      c.run(y, m, function (b, v, T) {
        if (b || !v || !T) return p(b);
        const x = v,
          X = c.stringify(x, T);
        (mS(X) ? (T.value = X) : (T.result = X), p(b, T));
      });
      function p(b, v) {
        b || !v ? d(b) : s ? s(v) : r(void 0, v);
      }
    }
  }
  processSync(u) {
    let r = !1,
      c;
    return (
      this.freeze(),
      Oo("processSync", this.parser || this.Parser),
      Do("processSync", this.compiler || this.Compiler),
      this.process(u, f),
      Qp("processSync", "process", r),
      c
    );
    function f(s, d) {
      ((r = !0), qp(s), (c = d));
    }
  }
  run(u, r, c) {
    (Xp(u), this.freeze());
    const f = this.transformers;
    return (
      !c && typeof r == "function" && ((c = r), (r = void 0)),
      c ? s(void 0, c) : new Promise(s)
    );
    function s(d, m) {
      const y = Yu(r);
      f.run(u, y, p);
      function p(b, v, T) {
        const x = v || u;
        b ? m(b) : d ? d(x) : c(void 0, x, T);
      }
    }
  }
  runSync(u, r) {
    let c = !1,
      f;
    return (this.run(u, r, s), Qp("runSync", "run", c), f);
    function s(d, m) {
      (qp(d), (f = m), (c = !0));
    }
  }
  stringify(u, r) {
    this.freeze();
    const c = Yu(r),
      f = this.compiler || this.Compiler;
    return (Do("stringify", f), Xp(u), f(u, c));
  }
  use(u, ...r) {
    const c = this.attachers,
      f = this.namespace;
    if ((Mo("use", this.frozen), u != null))
      if (typeof u == "function") y(u, r);
      else if (typeof u == "object") Array.isArray(u) ? m(u) : d(u);
      else throw new TypeError("Expected usable value, not `" + u + "`");
    return this;
    function s(p) {
      if (typeof p == "function") y(p, []);
      else if (typeof p == "object")
        if (Array.isArray(p)) {
          const [b, ...v] = p;
          y(b, v);
        } else d(p);
      else throw new TypeError("Expected usable value, not `" + p + "`");
    }
    function d(p) {
      if (!("plugins" in p) && !("settings" in p))
        throw new Error(
          "Expected usable value but received an empty preset, which is probably a mistake: presets typically come with `plugins` and sometimes with `settings`, but this has neither",
        );
      (m(p.plugins),
        p.settings && (f.settings = To(!0, f.settings, p.settings)));
    }
    function m(p) {
      let b = -1;
      if (p != null)
        if (Array.isArray(p))
          for (; ++b < p.length; ) {
            const v = p[b];
            s(v);
          }
        else throw new TypeError("Expected a list of plugins, not `" + p + "`");
    }
    function y(p, b) {
      let v = -1,
        T = -1;
      for (; ++v < c.length; )
        if (c[v][0] === p) {
          T = v;
          break;
        }
      if (T === -1) c.push([p, ...b]);
      else if (b.length > 0) {
        let [x, ...X] = b;
        const G = c[T][1];
        (Lo(G) && Lo(x) && (x = To(!0, G, x)), (c[T] = [p, x, ...X]));
      }
    }
  }
}
const dS = new ef().freeze();
function Oo(i, u) {
  if (typeof u != "function")
    throw new TypeError("Cannot `" + i + "` without `parser`");
}
function Do(i, u) {
  if (typeof u != "function")
    throw new TypeError("Cannot `" + i + "` without `compiler`");
}
function Mo(i, u) {
  if (u)
    throw new Error(
      "Cannot call `" +
        i +
        "` on a frozen processor.\nCreate a new processor first, by calling it: use `processor()` instead of `processor`.",
    );
}
function Xp(i) {
  if (!Lo(i) || typeof i.type != "string")
    throw new TypeError("Expected node, got `" + i + "`");
}
function Qp(i, u, r) {
  if (!r)
    throw new Error("`" + i + "` finished async. Use `" + u + "` instead");
}
function Yu(i) {
  return pS(i) ? i : new Dm(i);
}
function pS(i) {
  return !!(i && typeof i == "object" && "message" in i && "messages" in i);
}
function mS(i) {
  return typeof i == "string" || gS(i);
}
function gS(i) {
  return !!(
    i &&
    typeof i == "object" &&
    "byteLength" in i &&
    "byteOffset" in i
  );
}
const yS = "https://github.com/remarkjs/react-markdown/blob/main/changelog.md",
  Vp = [],
  Zp = { allowDangerousHtml: !0 },
  bS = /^(https?|ircs?|mailto|xmpp)$/i,
  vS = [
    { from: "astPlugins", id: "remove-buggy-html-in-markdown-parser" },
    { from: "allowDangerousHtml", id: "remove-buggy-html-in-markdown-parser" },
    {
      from: "allowNode",
      id: "replace-allownode-allowedtypes-and-disallowedtypes",
      to: "allowElement",
    },
    {
      from: "allowedTypes",
      id: "replace-allownode-allowedtypes-and-disallowedtypes",
      to: "allowedElements",
    },
    { from: "className", id: "remove-classname" },
    {
      from: "disallowedTypes",
      id: "replace-allownode-allowedtypes-and-disallowedtypes",
      to: "disallowedElements",
    },
    { from: "escapeHtml", id: "remove-buggy-html-in-markdown-parser" },
    { from: "includeElementIndex", id: "#remove-includeelementindex" },
    {
      from: "includeNodeIndex",
      id: "change-includenodeindex-to-includeelementindex",
    },
    { from: "linkTarget", id: "remove-linktarget" },
    {
      from: "plugins",
      id: "change-plugins-to-remarkplugins",
      to: "remarkPlugins",
    },
    { from: "rawSourcePos", id: "#remove-rawsourcepos" },
    {
      from: "renderers",
      id: "change-renderers-to-components",
      to: "components",
    },
    { from: "source", id: "change-source-to-children", to: "children" },
    { from: "sourcePos", id: "#remove-sourcepos" },
    { from: "transformImageUri", id: "#add-urltransform", to: "urlTransform" },
    { from: "transformLinkUri", id: "#add-urltransform", to: "urlTransform" },
  ];
function SS(i) {
  const u = xS(i),
    r = ES(i);
  return zS(u.runSync(u.parse(r), r), i);
}
function xS(i) {
  const u = i.rehypePlugins || Vp,
    r = i.remarkPlugins || Vp,
    c = i.remarkRehypeOptions ? { ...i.remarkRehypeOptions, ...Zp } : Zp;
  return dS().use(tv).use(r).use(Fv, c).use(u);
}
function ES(i) {
  const u = i.children || "",
    r = new Dm();
  return (typeof u == "string" && (r.value = u), r);
}
function zS(i, u) {
  const r = u.allowedElements,
    c = u.allowElement,
    f = u.components,
    s = u.disallowedElements,
    d = u.skipHtml,
    m = u.unwrapDisallowed,
    y = u.urlTransform || TS;
  for (const b of vS)
    Object.hasOwn(u, b.from) &&
      ("" +
        b.from +
        (b.to ? "use `" + b.to + "` instead" : "remove it") +
        yS +
        b.id,
      void 0);
  return (
    Om(i, p),
    N1(i, {
      Fragment: R.Fragment,
      components: f,
      ignoreInvalidStyle: !0,
      jsx: R.jsx,
      jsxs: R.jsxs,
      passKeys: !0,
      passNode: !0,
    })
  );
  function p(b, v, T) {
    if (b.type === "raw" && T && typeof v == "number")
      return (
        d
          ? T.children.splice(v, 1)
          : (T.children[v] = { type: "text", value: b.value }),
        v
      );
    if (b.type === "element") {
      let x;
      for (x in So)
        if (Object.hasOwn(So, x) && Object.hasOwn(b.properties, x)) {
          const X = b.properties[x],
            G = So[x];
          (G === null || G.includes(b.tagName)) &&
            (b.properties[x] = y(String(X || ""), x, b));
        }
    }
    if (b.type === "element") {
      let x = r ? !r.includes(b.tagName) : s ? s.includes(b.tagName) : !1;
      if (
        (!x && c && typeof v == "number" && (x = !c(b, v, T)),
        x && T && typeof v == "number")
      )
        return (
          m && b.children
            ? T.children.splice(v, 1, ...b.children)
            : T.children.splice(v, 1),
          v
        );
    }
  }
}
function TS(i) {
  const u = i.indexOf(":"),
    r = i.indexOf("?"),
    c = i.indexOf("#"),
    f = i.indexOf("/");
  return u === -1 ||
    (f !== -1 && u > f) ||
    (r !== -1 && u > r) ||
    (c !== -1 && u > c) ||
    bS.test(i.slice(0, u))
    ? i
    : "";
}
const Fu = "";
async function AS({ status: i, tags: u, limit: r = 20, offset: c = 0 } = {}) {
  const f = new URLSearchParams();
  (i && f.set("status", i),
    u && f.set("tags", u),
    f.set("limit", String(r)),
    f.set("offset", String(c)));
  const s = await fetch(`${Fu}/jobs?${f}`);
  if (!s.ok) throw new Error(await s.text());
  return s.json();
}
async function CS({ task: i, profile: u, tags: r, source: c = "dashboard" }) {
  const f = await fetch(`${Fu}/jobs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      task: i,
      profile: u || "",
      tags: r
        ? r
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean)
        : [],
      source: c,
    }),
  });
  if (!f.ok) throw new Error(await f.text());
  return f.json();
}
async function _S(i) {
  const u = await fetch(`${Fu}/jobs/${i}/cancel`, { method: "POST" });
  if (!u.ok) throw new Error(await u.text());
  return u.json();
}
async function OS(i) {
  const u = await fetch(`${Fu}/jobs/${i}/output`);
  if (!u.ok) throw new Error(await u.text());
  return u.json();
}
const Mm = {
    PENDING: "#6b7280",
    RUNNING: "#2563eb",
    SUCCEEDED: "#16a34a",
    FAILED: "#dc2626",
    CANCELLED: "#9ca3af",
  },
  DS = [
    { label: "All", key: null },
    { label: "Pending", key: "PENDING" },
    { label: "Running", key: "RUNNING" },
    { label: "Succeeded", key: "SUCCEEDED" },
    { label: "Failed", key: "FAILED" },
  ],
  MS = 200,
  kS = 1200,
  Kp = 5e3;
function wS(i) {
  const u = (Date.now() - new Date(i).getTime()) / 1e3;
  return u < 60
    ? `${Math.floor(u)}s`
    : u < 3600
      ? `${Math.floor(u / 60)}m`
      : u < 86400
        ? `${Math.floor(u / 3600)}h`
        : `${Math.floor(u / 86400)}d`;
}
function km(i, u) {
  if (!i) return "—";
  const r = (u ? new Date(u) : new Date()) - new Date(i),
    c = Math.floor(r / 1e3);
  return c < 60
    ? `${c}s`
    : c < 3600
      ? `${Math.floor(c / 60)}m ${c % 60}s`
      : `${Math.floor(c / 3600)}h ${Math.floor((c % 3600) / 60)}m`;
}
function wm(i) {
  return i
    ? i
        .split(
          `
`,
        )[0]
        .replace(/^#+\s*/, "")
        .trim()
    : "";
}
function Nm({ status: i }) {
  const u = Mm[i] || "#6b7280";
  return R.jsxs("span", {
    style: {
      position: "relative",
      display: "inline-flex",
      alignItems: "center",
    },
    children: [
      i === "RUNNING" &&
        R.jsx("span", {
          style: {
            position: "absolute",
            width: 10,
            height: 10,
            borderRadius: "50%",
            background: u,
            opacity: 0.4,
            animation: "ripple 1.4s ease-out infinite",
          },
        }),
      R.jsx("span", {
        style: {
          display: "inline-block",
          width: 8,
          height: 8,
          borderRadius: "50%",
          background: u,
          flexShrink: 0,
        },
      }),
    ],
  });
}
function Rm({ label: i, onClick: u, active: r }) {
  return R.jsx("span", {
    onClick: u,
    style: {
      display: "inline-block",
      padding: "1px 6px",
      borderRadius: 4,
      fontSize: 11,
      fontFamily: "monospace",
      background: r ? "#2563eb" : "#f1f5f9",
      color: r ? "#fff" : "#374151",
      cursor: u ? "pointer" : "default",
      userSelect: "none",
      border: r ? "1px solid #2563eb" : "1px solid #e2e8f0",
    },
    children: i,
  });
}
function Xu({ children: i }) {
  return R.jsx("kbd", {
    style: {
      display: "inline-block",
      padding: "1px 5px",
      borderRadius: 3,
      fontSize: 11,
      fontFamily: "monospace",
      background: "#f1f5f9",
      border: "1px solid #d1d5db",
      color: "#374151",
    },
    children: i,
  });
}
function NS({ allTags: i, activeTag: u, onSelect: r }) {
  const [c, f] = St.useState(!1),
    s = St.useRef(null);
  return (
    St.useEffect(() => {
      function d(m) {
        s.current && !s.current.contains(m.target) && f(!1);
      }
      return (
        document.addEventListener("mousedown", d),
        () => document.removeEventListener("mousedown", d)
      );
    }, []),
    i.length === 0
      ? null
      : R.jsxs("div", {
          ref: s,
          style: { position: "relative", display: "inline-block" },
          children: [
            R.jsx("button", {
              onClick: () => f((d) => !d),
              style: {
                padding: "3px 10px",
                borderRadius: 6,
                border: "1px solid #d1d5db",
                background: u ? "#2563eb" : "#fff",
                color: u ? "#fff" : "#374151",
                cursor: "pointer",
                fontSize: 13,
              },
              children: u ? `#${u}` : "Tags ▾",
            }),
            c &&
              R.jsxs("div", {
                style: {
                  position: "absolute",
                  top: "110%",
                  left: 0,
                  background: "#fff",
                  border: "1px solid #e2e8f0",
                  borderRadius: 8,
                  boxShadow: "0 4px 12px rgba(0,0,0,0.1)",
                  minWidth: 160,
                  zIndex: 100,
                  maxHeight: 300,
                  overflowY: "auto",
                },
                children: [
                  u &&
                    R.jsx("div", {
                      onClick: () => {
                        (r(null), f(!1));
                      },
                      style: {
                        padding: "8px 12px",
                        cursor: "pointer",
                        color: "#6b7280",
                        fontSize: 13,
                      },
                      children: "Clear filter",
                    }),
                  i.map(([d, m]) =>
                    R.jsxs(
                      "div",
                      {
                        onClick: () => {
                          (r(d), f(!1));
                        },
                        style: {
                          padding: "8px 12px",
                          cursor: "pointer",
                          display: "flex",
                          justifyContent: "space-between",
                          fontSize: 13,
                          background: d === u ? "#eff6ff" : "transparent",
                        },
                        children: [
                          R.jsxs("span", {
                            style: { fontFamily: "monospace" },
                            children: ["#", d],
                          }),
                          R.jsx("span", {
                            style: { color: "#9ca3af" },
                            children: m,
                          }),
                        ],
                      },
                      d,
                    ),
                  ),
                ],
              }),
          ],
        })
  );
}
function RS({ job: i, selected: u, dismissed: r, onSelect: c }) {
  var s;
  if (r) return null;
  const f =
    (s = i.attempts) != null && s.length
      ? i.attempts[i.attempts.length - 1]
      : null;
  return R.jsxs("div", {
    onClick: c,
    style: {
      padding: "10px 16px",
      borderBottom: "1px solid #f1f5f9",
      cursor: "pointer",
      background: u ? "#eff6ff" : "transparent",
      borderLeft: u ? "3px solid #2563eb" : "3px solid transparent",
      transition: "background 0.1s",
    },
    children: [
      R.jsxs("div", {
        style: {
          display: "flex",
          alignItems: "center",
          gap: 8,
          marginBottom: 4,
        },
        children: [
          R.jsx(Nm, { status: i.status }),
          R.jsx("span", {
            style: {
              fontFamily: "monospace",
              fontSize: 11,
              color: "#9ca3af",
              flexShrink: 0,
            },
            children: i.id.slice(-8),
          }),
          R.jsx("span", {
            style: {
              flex: 1,
              fontSize: 13,
              fontWeight: 500,
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            },
            title: i.task,
            children: wm(i.task),
          }),
          R.jsx("span", {
            style: { fontSize: 11, color: "#9ca3af", flexShrink: 0 },
            children: wS(i.created_at),
          }),
        ],
      }),
      R.jsxs("div", {
        style: {
          display: "flex",
          alignItems: "center",
          gap: 6,
          paddingLeft: 16,
        },
        children: [
          i.profile &&
            R.jsx("span", {
              style: {
                fontSize: 11,
                color: "#6b7280",
                background: "#f9fafb",
                border: "1px solid #e5e7eb",
                borderRadius: 3,
                padding: "0 4px",
              },
              children: i.profile,
            }),
          (i.tags || []).map((d) => R.jsx(Rm, { label: d }, d)),
          f &&
            R.jsx("span", {
              style: { fontSize: 11, color: "#9ca3af", marginLeft: "auto" },
              children: km(f.started_at, f.finished_at),
            }),
        ],
      }),
    ],
  });
}
function US({ job: i, output: u, onCancel: r, onFollowOn: c, onDismiss: f }) {
  var d, m;
  const s =
    (d = i.attempts) != null && d.length
      ? i.attempts[i.attempts.length - 1]
      : null;
  return R.jsxs("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      height: "100%",
      overflow: "hidden",
    },
    children: [
      R.jsxs("div", {
        style: {
          padding: "16px 20px",
          borderBottom: "1px solid #e5e7eb",
          flexShrink: 0,
        },
        children: [
          R.jsxs("div", {
            style: {
              display: "flex",
              alignItems: "center",
              gap: 10,
              marginBottom: 8,
            },
            children: [
              R.jsx(Nm, { status: i.status }),
              R.jsx("span", {
                style: {
                  fontSize: 13,
                  fontWeight: 600,
                  flex: 1,
                  color: Mm[i.status],
                },
                children: i.status,
              }),
              R.jsx("span", {
                style: {
                  fontFamily: "monospace",
                  fontSize: 11,
                  color: "#9ca3af",
                },
                children: i.id,
              }),
            ],
          }),
          R.jsx("div", {
            style: {
              fontSize: 15,
              fontWeight: 600,
              color: "#111827",
              marginBottom: 4,
              lineHeight: 1.4,
            },
            children: wm(i.task),
          }),
          i.task.includes(`
`) &&
            R.jsx("div", {
              style: {
                fontSize: 12,
                color: "#6b7280",
                marginBottom: 10,
                lineHeight: 1.5,
                whiteSpace: "pre-wrap",
                maxHeight: 80,
                overflow: "hidden",
                maskImage:
                  "linear-gradient(to bottom, black 60%, transparent 100%)",
              },
              children: i.task
                .slice(
                  i.task.indexOf(`
`) + 1,
                )
                .trim(),
            }),
          R.jsxs("div", {
            style: {
              display: "flex",
              gap: 6,
              flexWrap: "wrap",
              marginBottom: 10,
            },
            children: [
              (i.tags || []).map((y) => R.jsx(Rm, { label: y }, y)),
              i.profile &&
                R.jsxs("span", {
                  style: {
                    fontSize: 11,
                    color: "#6b7280",
                    background: "#f9fafb",
                    border: "1px solid #e5e7eb",
                    borderRadius: 3,
                    padding: "0 6px",
                  },
                  children: ["profile: ", i.profile],
                }),
            ],
          }),
          R.jsxs("div", {
            style: { fontSize: 11, color: "#9ca3af", display: "flex", gap: 16 },
            children: [
              R.jsxs("span", {
                children: ["Created ", new Date(i.created_at).toLocaleString()],
              }),
              s &&
                R.jsxs("span", {
                  children: ["Duration: ", km(s.started_at, s.finished_at)],
                }),
              ((m = i.attempts) == null ? void 0 : m.length) > 0 &&
                R.jsxs("span", { children: ["Attempts: ", i.attempts.length] }),
              typeof (s == null ? void 0 : s.exit_code) == "number" &&
                R.jsxs("span", { children: ["Exit: ", s.exit_code] }),
            ],
          }),
          R.jsxs("div", {
            style: { display: "flex", gap: 8, marginTop: 12 },
            children: [
              (i.status === "PENDING" || i.status === "RUNNING") &&
                R.jsxs("button", {
                  onClick: r,
                  style: {
                    padding: "4px 12px",
                    borderRadius: 6,
                    border: "1px solid #fca5a5",
                    background: "#fff1f2",
                    color: "#dc2626",
                    cursor: "pointer",
                    fontSize: 12,
                  },
                  children: ["Cancel ", R.jsx(Xu, { children: "c" })],
                }),
              R.jsxs("button", {
                onClick: c,
                style: {
                  padding: "4px 12px",
                  borderRadius: 6,
                  border: "1px solid #d1d5db",
                  background: "#f9fafb",
                  color: "#374151",
                  cursor: "pointer",
                  fontSize: 12,
                },
                children: ["Follow-on ", R.jsx(Xu, { children: "f" })],
              }),
              R.jsxs("button", {
                onClick: f,
                style: {
                  padding: "4px 12px",
                  borderRadius: 6,
                  border: "1px solid #d1d5db",
                  background: "#f9fafb",
                  color: "#374151",
                  cursor: "pointer",
                  fontSize: 12,
                },
                children: ["Dismiss ", R.jsx(Xu, { children: "e" })],
              }),
            ],
          }),
        ],
      }),
      R.jsx("div", {
        style: { flex: 1, overflow: "auto", padding: "16px 20px" },
        children: u
          ? R.jsxs(R.Fragment, {
              children: [
                u.truncated &&
                  R.jsx("div", {
                    style: {
                      padding: "6px 10px",
                      background: "#fffbeb",
                      border: "1px solid #fde68a",
                      borderRadius: 4,
                      fontSize: 12,
                      color: "#92400e",
                      marginBottom: 10,
                    },
                    children: "Output truncated — showing tail only",
                  }),
                R.jsx("div", {
                  className: "md-output",
                  children: R.jsx(SS, { children: u.output }),
                }),
              ],
            })
          : s
            ? R.jsx("div", {
                style: { color: "#9ca3af", fontSize: 13 },
                children: "Loading output…",
              })
            : R.jsx("div", {
                style: { color: "#9ca3af", fontSize: 13 },
                children: "No output yet.",
              }),
      }),
    ],
  });
}
function BS({ onClose: i, onSubmit: u, prefill: r }) {
  const [c, f] = St.useState((r == null ? void 0 : r.task) || ""),
    [s, d] = St.useState((r == null ? void 0 : r.profile) || ""),
    [m, y] = St.useState((r == null ? void 0 : r.tags) || ""),
    [p, b] = St.useState(!1),
    [v, T] = St.useState(null),
    x = St.useRef(null);
  (St.useEffect(() => {
    var G;
    (G = x.current) == null || G.focus();
  }, []),
    St.useEffect(() => {
      function G(F) {
        F.key === "Escape" && i();
      }
      return (
        window.addEventListener("keydown", G),
        () => window.removeEventListener("keydown", G)
      );
    }, [i]));
  async function X(G) {
    if ((G.preventDefault(), !!c.trim())) {
      (b(!0), T(null));
      try {
        (await u({ task: c.trim(), profile: s, tags: m }), i());
      } catch (F) {
        (T(F.message), b(!1));
      }
    }
  }
  return R.jsx("div", {
    style: {
      position: "fixed",
      inset: 0,
      background: "rgba(0,0,0,0.4)",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      zIndex: 200,
    },
    onClick: (G) => G.target === G.currentTarget && i(),
    children: R.jsxs("div", {
      style: {
        background: "#fff",
        borderRadius: 12,
        padding: 28,
        width: 560,
        maxWidth: "95vw",
        boxShadow: "0 20px 60px rgba(0,0,0,0.15)",
      },
      children: [
        R.jsx("h2", {
          style: { margin: "0 0 20px", fontSize: 18, fontWeight: 600 },
          children: "Submit Job",
        }),
        R.jsxs("form", {
          onSubmit: X,
          children: [
            R.jsxs("div", {
              style: { marginBottom: 16 },
              children: [
                R.jsx("label", {
                  style: {
                    display: "block",
                    fontSize: 13,
                    fontWeight: 500,
                    marginBottom: 6,
                  },
                  children: "Task *",
                }),
                R.jsx("textarea", {
                  ref: x,
                  value: c,
                  onChange: (G) => f(G.target.value),
                  placeholder: "Describe the task for the agent…",
                  rows: 5,
                  style: {
                    width: "100%",
                    padding: "8px 12px",
                    borderRadius: 8,
                    border: "1px solid #d1d5db",
                    fontSize: 14,
                    fontFamily: "inherit",
                    resize: "vertical",
                    boxSizing: "border-box",
                  },
                }),
              ],
            }),
            R.jsxs("div", {
              style: { display: "flex", gap: 12, marginBottom: 16 },
              children: [
                R.jsxs("div", {
                  style: { flex: 1 },
                  children: [
                    R.jsx("label", {
                      style: {
                        display: "block",
                        fontSize: 13,
                        fontWeight: 500,
                        marginBottom: 6,
                      },
                      children: "Profile",
                    }),
                    R.jsxs("select", {
                      value: s,
                      onChange: (G) => d(G.target.value),
                      style: {
                        width: "100%",
                        padding: "8px 10px",
                        borderRadius: 8,
                        border: "1px solid #d1d5db",
                        fontSize: 14,
                        background: "#fff",
                      },
                      children: [
                        R.jsx("option", { value: "", children: "Default" }),
                        R.jsx("option", {
                          value: "ci-debug",
                          children: "ci-debug",
                        }),
                        R.jsx("option", {
                          value: "code-fix",
                          children: "code-fix",
                        }),
                      ],
                    }),
                  ],
                }),
                R.jsxs("div", {
                  style: { flex: 1 },
                  children: [
                    R.jsx("label", {
                      style: {
                        display: "block",
                        fontSize: 13,
                        fontWeight: 500,
                        marginBottom: 6,
                      },
                      children: "Tags (comma-separated)",
                    }),
                    R.jsx("input", {
                      value: m,
                      onChange: (G) => y(G.target.value),
                      placeholder: "e.g. ci, homelab",
                      style: {
                        width: "100%",
                        padding: "8px 12px",
                        borderRadius: 8,
                        border: "1px solid #d1d5db",
                        fontSize: 14,
                        boxSizing: "border-box",
                      },
                    }),
                  ],
                }),
              ],
            }),
            v &&
              R.jsx("div", {
                style: {
                  marginBottom: 12,
                  padding: "8px 12px",
                  background: "#fef2f2",
                  border: "1px solid #fca5a5",
                  borderRadius: 6,
                  fontSize: 13,
                  color: "#dc2626",
                },
                children: v,
              }),
            R.jsxs("div", {
              style: { display: "flex", justifyContent: "flex-end", gap: 10 },
              children: [
                R.jsx("button", {
                  type: "button",
                  onClick: i,
                  style: {
                    padding: "8px 18px",
                    borderRadius: 8,
                    border: "1px solid #d1d5db",
                    background: "#fff",
                    cursor: "pointer",
                    fontSize: 14,
                  },
                  children: "Cancel",
                }),
                R.jsx("button", {
                  type: "submit",
                  disabled: p || !c.trim(),
                  style: {
                    padding: "8px 18px",
                    borderRadius: 8,
                    border: "none",
                    background: p || !c.trim() ? "#93c5fd" : "#2563eb",
                    color: "#fff",
                    cursor: p || !c.trim() ? "not-allowed" : "pointer",
                    fontSize: 14,
                    fontWeight: 500,
                  },
                  children: p ? "Submitting…" : "Submit",
                }),
              ],
            }),
          ],
        }),
      ],
    }),
  });
}
function jS({ onClose: i }) {
  St.useEffect(() => {
    function r(c) {
      (c.key === "Escape" || c.key === "?") && i();
    }
    return (
      window.addEventListener("keydown", r),
      () => window.removeEventListener("keydown", r)
    );
  }, [i]);
  const u = [
    ["j / ↓", "Select next job"],
    ["k / ↑", "Select previous job"],
    ["n", "New job"],
    ["e", "Dismiss selected"],
    ["c", "Cancel selected"],
    ["f", "Follow-on job"],
    ["1–5", "Switch filter tab"],
    ["?", "Toggle help"],
  ];
  return R.jsx("div", {
    style: {
      position: "fixed",
      inset: 0,
      background: "rgba(0,0,0,0.4)",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      zIndex: 200,
    },
    onClick: (r) => r.target === r.currentTarget && i(),
    children: R.jsxs("div", {
      style: {
        background: "#fff",
        borderRadius: 12,
        padding: 28,
        width: 400,
        boxShadow: "0 20px 60px rgba(0,0,0,0.15)",
      },
      children: [
        R.jsx("h2", {
          style: { margin: "0 0 16px", fontSize: 18, fontWeight: 600 },
          children: "Keyboard Shortcuts",
        }),
        R.jsx("table", {
          style: { width: "100%", borderCollapse: "collapse" },
          children: R.jsx("tbody", {
            children: u.map(([r, c]) =>
              R.jsxs(
                "tr",
                {
                  children: [
                    R.jsx("td", {
                      style: { padding: "6px 0", width: 80 },
                      children: R.jsx(Xu, { children: r }),
                    }),
                    R.jsx("td", {
                      style: {
                        padding: "6px 0",
                        fontSize: 13,
                        color: "#374151",
                      },
                      children: c,
                    }),
                  ],
                },
                r,
              ),
            ),
          }),
        }),
        R.jsx("div", {
          style: { marginTop: 16, textAlign: "right" },
          children: R.jsx("button", {
            onClick: i,
            style: {
              padding: "6px 16px",
              borderRadius: 8,
              border: "1px solid #d1d5db",
              background: "#fff",
              cursor: "pointer",
              fontSize: 13,
            },
            children: "Close",
          }),
        }),
      ],
    }),
  });
}
function HS() {
  var zt;
  const [i, u] = St.useState([]),
    [r, c] = St.useState(0),
    [f, s] = St.useState(!0),
    [d, m] = St.useState(null),
    [y, p] = St.useState(null),
    [b, v] = St.useState(new Set()),
    [T, x] = St.useState(null),
    [X, G] = St.useState(null),
    [F, Y] = St.useState(!1),
    [it, K] = St.useState(!1),
    [mt, yt] = St.useState(null),
    [H, W] = St.useState(null),
    [ht, pt] = St.useState(400),
    Et = St.useRef(!1),
    tt = St.useRef(0),
    $ = St.useRef(0),
    [_t, lt] = St.useState(window.innerWidth),
    Q = _t < 768,
    M = St.useCallback(async () => {
      try {
        const V = await AS({
          status: T || void 0,
          tags: X || void 0,
          limit: 100,
        });
        (u(V.jobs || []), c(V.total || 0), m(null));
      } catch (V) {
        m(V.message);
      } finally {
        s(!1);
      }
    }, [T, X]);
  (St.useEffect(() => {
    (s(!0), M());
    const V = setInterval(M, Kp);
    return () => clearInterval(V);
  }, [M]),
    St.useEffect(() => {
      const V = () => lt(window.innerWidth);
      return (
        window.addEventListener("resize", V),
        () => window.removeEventListener("resize", V)
      );
    }, []));
  const B = St.useMemo(() => i.find((V) => V.id === y) || null, [i, y]);
  St.useEffect(() => {
    var kt;
    if (!B) {
      W(null);
      return;
    }
    if (!((kt = B.attempts) != null && kt.length)) {
      W(null);
      return;
    }
    let V = !1;
    async function ut() {
      try {
        const me = await OS(B.id);
        V || W(me);
      } catch {
        V || W(null);
      }
    }
    if ((ut(), B.status === "RUNNING")) {
      const me = setInterval(ut, Kp);
      return () => {
        ((V = !0), clearInterval(me));
      };
    }
    return () => {
      V = !0;
    };
  }, [
    B == null ? void 0 : B.id,
    B == null ? void 0 : B.status,
    (zt = B == null ? void 0 : B.attempts) == null ? void 0 : zt.length,
  ]);
  const P = St.useMemo(() => i.filter((V) => !b.has(V.id)), [i, b]),
    xt = St.useMemo(() => {
      const V = {};
      return (
        i.forEach((ut) =>
          (ut.tags || []).forEach((kt) => (V[kt] = (V[kt] || 0) + 1)),
        ),
        Object.entries(V).sort((ut, kt) => kt[1] - ut[1])
      );
    }, [i]),
    E = St.useMemo(() => {
      const V = {
        running: 0,
        pending: 0,
        succeeded: 0,
        failed: 0,
        cancelled: 0,
      };
      return (
        i.forEach((ut) => {
          const kt = ut.status.toLowerCase();
          kt in V && V[kt]++;
        }),
        V
      );
    }, [i]),
    A = St.useMemo(() => P.findIndex((V) => V.id === y), [P, y]);
  function U(V) {
    var kt;
    const ut = Math.max(0, Math.min(V, P.length - 1));
    p(((kt = P[ut]) == null ? void 0 : kt.id) || null);
  }
  St.useEffect(() => {
    function V(ut) {
      if (
        !(F || it) &&
        !(
          ut.target.tagName === "INPUT" ||
          ut.target.tagName === "TEXTAREA" ||
          ut.target.tagName === "SELECT"
        )
      )
        switch (ut.key) {
          case "j":
          case "ArrowDown":
            (ut.preventDefault(), U(A + 1));
            break;
          case "k":
          case "ArrowUp":
            (ut.preventDefault(), U(A - 1));
            break;
          case "n":
            (yt(null), Y(!0));
            break;
          case "e":
            y && v((kt) => new Set([...kt, y]));
            break;
          case "c":
            B && (B.status === "PENDING" || B.status === "RUNNING") && S(B);
            break;
          case "f":
            B && I(B);
            break;
          case "?":
            K((kt) => !kt);
            break;
          case "1":
            x(null);
            break;
          case "2":
            x("PENDING");
            break;
          case "3":
            x("RUNNING");
            break;
          case "4":
            x("SUCCEEDED");
            break;
          case "5":
            x("FAILED");
            break;
        }
    }
    return (
      window.addEventListener("keydown", V),
      () => window.removeEventListener("keydown", V)
    );
  }, [F, it, A, y, B, P]);
  async function S(V) {
    try {
      (await _S(V.id), M());
    } catch (ut) {
      alert("Cancel failed: " + ut.message);
    }
  }
  function I(V) {
    const ut =
      H != null && H.output
        ? `

Previous output tail:
` + H.output.slice(-500)
        : "";
    (yt({
      task: `Follow-on to job ${V.id.slice(-8)}: ${V.task}${ut}`,
      profile: V.profile || "",
      tags: (V.tags || []).join(", "),
    }),
      Y(!0));
  }
  async function ct({ task: V, profile: ut, tags: kt }) {
    (await CS({ task: V, profile: ut, tags: kt }), M());
  }
  function at(V) {
    ((Et.current = !0),
      (tt.current = V.clientX),
      ($.current = ht),
      V.preventDefault());
  }
  return (
    St.useEffect(() => {
      function V(kt) {
        if (!Et.current) return;
        const me = tt.current - kt.clientX;
        pt(Math.max(MS, Math.min(kS, $.current + me)));
      }
      function ut() {
        Et.current = !1;
      }
      return (
        window.addEventListener("mousemove", V),
        window.addEventListener("mouseup", ut),
        () => {
          (window.removeEventListener("mousemove", V),
            window.removeEventListener("mouseup", ut));
        }
      );
    }, []),
    R.jsxs("div", {
      style: {
        height: "100vh",
        display: "flex",
        flexDirection: "column",
        fontFamily: "system-ui, sans-serif",
        background: "#f8fafc",
      },
      children: [
        R.jsx("style", {
          children: `
        @keyframes ripple {
          0% { transform: scale(1); opacity: 0.4; }
          100% { transform: scale(3); opacity: 0; }
        }
        * { box-sizing: border-box; }
        body { margin: 0; }

        /* Markdown output pane */
        .md-output { font-size: 13px; line-height: 1.65; color: #1f2937; }
        .md-output p { margin: 0 0 10px; }
        .md-output p:last-child { margin-bottom: 0; }
        .md-output h1, .md-output h2, .md-output h3,
        .md-output h4, .md-output h5, .md-output h6 {
          margin: 16px 0 6px; font-weight: 600; line-height: 1.3;
        }
        .md-output h1 { font-size: 18px; }
        .md-output h2 { font-size: 16px; }
        .md-output h3 { font-size: 14px; }
        .md-output ul, .md-output ol { margin: 0 0 10px; padding-left: 22px; }
        .md-output li { margin-bottom: 3px; }
        .md-output li input[type="checkbox"] { margin-right: 5px; }
        .md-output code {
          font-family: monospace; font-size: 12px;
          background: #f1f5f9; border-radius: 3px; padding: 1px 4px;
        }
        .md-output pre {
          background: #1e293b; border-radius: 6px;
          padding: 12px 14px; overflow-x: auto; margin: 0 0 12px;
        }
        .md-output pre code {
          background: none; padding: 0; color: #e2e8f0;
          font-size: 12px; line-height: 1.6;
        }
        .md-output blockquote {
          border-left: 3px solid #d1d5db; margin: 0 0 10px;
          padding: 4px 12px; color: #6b7280;
        }
        .md-output a { color: #2563eb; text-decoration: underline; }
        .md-output hr { border: none; border-top: 1px solid #e5e7eb; margin: 12px 0; }
        .md-output table { border-collapse: collapse; width: 100%; margin-bottom: 10px; font-size: 12px; }
        .md-output th, .md-output td { border: 1px solid #e5e7eb; padding: 5px 10px; text-align: left; }
        .md-output th { background: #f8fafc; font-weight: 600; }
      `,
        }),
        R.jsxs("div", {
          style: {
            minHeight: 52,
            background: "#fff",
            borderBottom: "1px solid #e5e7eb",
            display: "flex",
            alignItems: "center",
            padding: "0 16px",
            gap: Q ? 8 : 20,
            flexShrink: 0,
            flexWrap: Q ? "wrap" : "nowrap",
            paddingTop: Q ? 8 : 0,
            paddingBottom: Q ? 8 : 0,
          },
          children: [
            R.jsx("span", {
              style: { fontWeight: 700, fontSize: 16, color: "#111827" },
              children: "🦆 Agent Orchestrator",
            }),
            !Q &&
              R.jsxs("div", {
                style: {
                  display: "flex",
                  gap: 16,
                  fontSize: 12,
                  color: "#6b7280",
                },
                children: [
                  R.jsxs("span", {
                    children: [
                      R.jsx("span", {
                        style: { color: "#2563eb", fontWeight: 600 },
                        children: E.running,
                      }),
                      " ",
                      "running",
                    ],
                  }),
                  R.jsxs("span", {
                    children: [
                      R.jsx("span", {
                        style: { color: "#6b7280", fontWeight: 600 },
                        children: E.pending,
                      }),
                      " ",
                      "pending",
                    ],
                  }),
                  R.jsxs("span", {
                    children: [
                      R.jsx("span", {
                        style: { color: "#16a34a", fontWeight: 600 },
                        children: E.succeeded,
                      }),
                      " ",
                      "succeeded",
                    ],
                  }),
                  R.jsxs("span", {
                    children: [
                      R.jsx("span", {
                        style: { color: "#dc2626", fontWeight: 600 },
                        children: E.failed,
                      }),
                      " ",
                      "failed",
                    ],
                  }),
                ],
              }),
            R.jsxs("div", {
              style: { marginLeft: "auto", display: "flex", gap: 8 },
              children: [
                !Q &&
                  R.jsx("button", {
                    onClick: () => K(!0),
                    style: {
                      padding: "5px 12px",
                      borderRadius: 6,
                      border: "1px solid #d1d5db",
                      background: "#fff",
                      cursor: "pointer",
                      fontSize: 13,
                      color: "#374151",
                    },
                    children: "? Help",
                  }),
                R.jsx("button", {
                  onClick: () => {
                    (yt(null), Y(!0));
                  },
                  style: {
                    padding: "5px 14px",
                    borderRadius: 6,
                    border: "none",
                    background: "#2563eb",
                    color: "#fff",
                    cursor: "pointer",
                    fontSize: 13,
                    fontWeight: 500,
                  },
                  children: "+ New Job",
                }),
              ],
            }),
          ],
        }),
        R.jsxs("div", {
          style: {
            height: 44,
            background: "#fff",
            borderBottom: "1px solid #e5e7eb",
            display: "flex",
            alignItems: "center",
            padding: "0 16px",
            gap: 4,
            flexShrink: 0,
            overflowX: Q ? "auto" : "visible",
            WebkitOverflowScrolling: "touch",
          },
          children: [
            DS.map((V) =>
              R.jsx(
                "button",
                {
                  onClick: () => x(V.key),
                  style: {
                    padding: "4px 14px",
                    borderRadius: 6,
                    border: "none",
                    background: T === V.key ? "#eff6ff" : "transparent",
                    color: T === V.key ? "#2563eb" : "#6b7280",
                    fontWeight: T === V.key ? 600 : 400,
                    cursor: "pointer",
                    fontSize: 13,
                    flexShrink: 0,
                  },
                  children: V.label,
                },
                V.label,
              ),
            ),
            R.jsx("div", {
              style: { marginLeft: "auto" },
              children: R.jsx(NS, { allTags: xt, activeTag: X, onSelect: G }),
            }),
            R.jsxs("span", {
              style: { fontSize: 12, color: "#9ca3af", marginLeft: 8 },
              children: [r, " total"],
            }),
          ],
        }),
        R.jsxs("div", {
          style: { flex: 1, display: "flex", overflow: "hidden" },
          children: [
            R.jsxs("div", {
              style: {
                flex: 1,
                overflowY: "auto",
                background: "#fff",
                borderRight: "1px solid #e5e7eb",
                display: Q && B ? "none" : "block",
              },
              children: [
                f &&
                  R.jsx("div", {
                    style: {
                      padding: 32,
                      color: "#9ca3af",
                      textAlign: "center",
                      fontSize: 13,
                    },
                    children: "Loading…",
                  }),
                d &&
                  R.jsxs("div", {
                    style: {
                      margin: 16,
                      padding: 12,
                      background: "#fef2f2",
                      border: "1px solid #fca5a5",
                      borderRadius: 6,
                      fontSize: 13,
                      color: "#dc2626",
                    },
                    children: ["Error: ", d],
                  }),
                !f &&
                  !d &&
                  P.length === 0 &&
                  R.jsx("div", {
                    style: {
                      padding: 40,
                      color: "#9ca3af",
                      textAlign: "center",
                      fontSize: 13,
                    },
                    children: "No jobs found.",
                  }),
                P.map((V) =>
                  R.jsx(
                    RS,
                    {
                      job: V,
                      selected: V.id === y,
                      dismissed: !1,
                      onSelect: () => p(V.id === y ? null : V.id),
                    },
                    V.id,
                  ),
                ),
              ],
            }),
            B &&
              R.jsxs(R.Fragment, {
                children: [
                  !Q &&
                    R.jsx("div", {
                      onMouseDown: at,
                      style: {
                        width: 4,
                        cursor: "col-resize",
                        background: "#e5e7eb",
                        flexShrink: 0,
                        transition: "background 0.15s",
                      },
                      onMouseEnter: (V) =>
                        (V.currentTarget.style.background = "#93c5fd"),
                      onMouseLeave: (V) =>
                        (V.currentTarget.style.background = "#e5e7eb"),
                    }),
                  R.jsxs("div", {
                    style: {
                      width: Q ? "100%" : ht,
                      flexShrink: 0,
                      overflowY: "auto",
                      background: "#fff",
                    },
                    children: [
                      Q &&
                        R.jsx("div", {
                          style: {
                            padding: "10px 16px",
                            borderBottom: "1px solid #e5e7eb",
                          },
                          children: R.jsx("button", {
                            onClick: () => p(null),
                            style: {
                              display: "flex",
                              alignItems: "center",
                              gap: 4,
                              padding: "5px 10px",
                              borderRadius: 6,
                              border: "1px solid #d1d5db",
                              background: "#fff",
                              cursor: "pointer",
                              fontSize: 13,
                              color: "#374151",
                            },
                            children: "← Back",
                          }),
                        }),
                      R.jsx(US, {
                        job: B,
                        output: H,
                        onCancel: () => S(B),
                        onFollowOn: () => I(B),
                        onDismiss: () => {
                          (v((V) => new Set([...V, B.id])), p(null));
                        },
                      }),
                    ],
                  }),
                ],
              }),
          ],
        }),
        F && R.jsx(BS, { prefill: mt, onClose: () => Y(!1), onSubmit: ct }),
        it && R.jsx(jS, { onClose: () => K(!1) }),
      ],
    })
  );
}
i1.createRoot(document.getElementById("root")).render(
  R.jsx(St.StrictMode, { children: R.jsx(HS, {}) }),
);
