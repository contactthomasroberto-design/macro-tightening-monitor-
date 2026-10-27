# Methodology

Equations implemented in `src/macro/`. Notation: $\pi$ inflation (%), $i$ policy rate, $u$
unemployment, $u^*$ its natural rate, $y$ output gap (% of potential), $r^*$ neutral real rate.
HAC = Newey-West standard errors with bandwidth $\lfloor 4 (T/100)^{2/9} \rfloor$ unless stated.

## 1. Data discipline

An observation for reference period $p$ is available from $\text{end}(p) + \ell$, with $\ell$ the
release lag in `config/series.yaml`. At an information date $d$ a model uses only
$\{x_p : \text{end}(p) + \ell \le d\}$. With ALFRED vintages, the value is the most recent vintage
$v \le d$.

## 2. Inflation (`inflation.py`)

Momentum: $a_k = 100\left[(P_t/P_{t-k})^{12/k} - 1\right]$, $k \in \{1, 3, 6\}$; yoy $= 100(P_t/P_{t-12}-1)$.

Persistence: $\pi_t = c + \sum_{j=1}^{p} \phi_j \pi_{t-j} + \varepsilon_t$, $p$ by BIC;
$\rho = \sum_j \phi_j$, $\operatorname{se}(\rho) = \sqrt{\mathbf 1' V \mathbf 1}$.
Half-life: first $h$ with impulse response $< 0.5$.

Energy pass-through:
$$\Delta \log P^{\text{head}}_t - \Delta \log P^{\text{core}}_t = a + \sum_{j=0}^{6} b_j \, \Delta \log \text{Oil}_{t-j} + \varepsilon_t, \qquad B = \sum_j b_j .$$

GSCPI local projections (Jordà 2005):
$$100(\log y_{t+h} - \log y_{t-1}) = a_h + b_h\, \text{GSCPI}_t + \sum_{j=1}^{3} c_j \Delta \log y_{t-j} + \sum_{j=1}^{3} d_j \text{GSCPI}_{t-j} + e_{t+h}.$$

Expectations factor: $z_{it} = (x_{it} - m_i)/s_i$; $f_t$ = first principal component;
$F_t = m_a + s_a (f_t - \bar f)/\operatorname{sd}(f)$ with $a$ = SPF 10-year CPI. Anchoring:
rolling $\Delta F_t = \alpha + \beta \Delta \pi_t + e_t$ (60 months).

Forecasts of $\pi_{t+h}$ (direct): random walk $\pi_t$; AR $c + \sum_{j<p}\phi_j \pi_{t-j}$;
Phillips $c + \phi\pi_t + \beta \tilde u_t + \gamma \Delta_{12}\log \text{Oil}_t + \delta E^{10y}_t$;
mixed-frequency $\Delta \log P^{\text{head}}_{t+k} = w_c \bar c + w_e g\, \text{oil}^{\text{mtd}}_t \mathbb 1_{k=1} + w_f \bar f$;
elastic net; equal-weight combination. Density $N(\hat\pi, \sigma_h^2)$, $\sigma_h$ = RMSE of the
model's own past out-of-sample errors.

Evaluation: RMSE, MAE; log score $\log \phi((y-\mu)/\sigma) - \log\sigma$;
$\text{CRPS} = \sigma\left[z(2\Phi(z)-1) + 2\phi(z) - \pi^{-1/2}\right]$; PIT $=\Phi((y-\mu)/\sigma)$;
Diebold-Mariano with Harvey-Leybourne-Newbold correction.

## 3. Policy (`policy.py`)

Taylor: $i = r^* + \pi^* + a_\pi(\pi - \pi^*) + a_y y$ (1993: $a_\pi = 1.5$, $a_y = 0.5$); balanced
approach $a_y = 1$; unemployment gap $y \approx -\kappa (u - u^*)$; first difference
$i_t = i_{t-1} + 0.5(\pi_t - \pi^*) + 0.5 \Delta_4 y_t$; inertial $i_t = \rho i_{t-1} + (1-\rho) i^{T}_t$.

Reaction function: $i_t = \rho i_{t-1} + (1-\rho)(a + b\pi_t + c y_t) + \varepsilon_t$, estimated as
$i_t = \alpha + \rho i_{t-1} + \beta\pi_t + \gamma y_t + \varepsilon_t$; $b = \beta/(1-\rho)$,
$c = \gamma/(1-\rho)$ with delta-method s.e.; Taylor principle $H_0: b \le 1$.

Reverse view: $\pi = \pi^* + (i^{\text{priced}} - r^* - \pi^* - a_y y)/a_\pi$.

## 4. Financial conditions (`fincond.py`)

$g_{t,t+4} = c + \sum_k \beta_k \Delta_L x_{k,t} + \phi g_{t-4,t} + e_t$ (ridge, CV penalty);
$\text{FCI}_t = -\sum_k \beta_k \Delta_L x_{k,t}$ (+ = headwind). Neutral FCI: $\text{FCI}^* = y_t\cdot 4/H$.
Gap $=\text{FCI}^* - \text{FCI}_t$; equivalence $\Delta x_k = -\text{gap}/\beta_k$.

## 5. Curves (`curves.py`)

$\text{3m10y} = y^{10} - y^{3m}$, $\text{2s10s} = y^{10} - y^{2}$, fly $= 2y^5 - y^2 - y^{10}$.
$y^{10} = r^{10} + \text{BE}^{10}$; $y^{10} = \bar i^{\,e} + \text{TP}$ (published models).
Stress: $z_t = (s_t - \bar s_{\le t})/\operatorname{sd}_{\le t}(s)$.

## 6. Growth and recession (`growth.py`, `recession.py`)

DFM: $x_{it} = \lambda_i' f_t + e_{it}$, $f_t = A_1 f_{t-1} + A_2 f_{t-2} + u_t$, $e_{it}$ AR(1); quarterly
GDP growth tied to monthly factors (Mariano-Murasawa). News: $\Delta \hat y = \sum_j w_j (x_j - E_{\text{old}}[x_j])$ + revisions.

Growth-at-Risk: $Q_\tau(\bar g_{t+1:t+h} \mid g_t, \text{NFCI}_t) = \beta_\tau'(1, g_t, \text{NFCI}_t)'$;
Jones-Faddy skew $t$ fitted to $\tau \in \{0.05, 0.25, 0.75, 0.95\}$;
$\text{ES}_{5\%} = 20\int_0^{0.05} Q(u)\,du$.

Recession: $P(\text{REC}_{t+12} = 1) = \Phi(a + b' x_t)$; AUC (Mann-Whitney), Brier; Sahm
$\bar u^{(3)}_t - \min_{12}\bar u^{(3)} \ge 0.5$.

## 7. Transmission (`transmission.py`)

$r^{eq}_t = a + b_r \Delta r^{10}_t + b_{be} \Delta \text{BE}^{10}_t + e_t$; event paths $x_{e+k} - x_{e-6}$;
LP $y_{t+h} - y_{t-1} = a_h + b_h s_t + e$, $s_t = \Delta y^2_t$ on decision days;
FX $100\log \text{FX}_t = a + b\,\text{diff}_t + u_t$.

## 8. Scenarios and fans (`scenarios.py`, `fans.py`)

$\pi_t = c + \rho\pi_{t-1} + \kappa(u^* - u_t) + \theta\Delta_4\log\text{Oil}_t + \iota^s_t + \varepsilon_t$;
$u_t = u_0 + \Delta u^s_t + v_t$, $v_t = 0.5 v_{t-1} + w_t$;
$i_t = i_{t-1} + \operatorname{clip}(\rho_i i_{t-1} + (1-\rho_i)(a + b\pi_t + c y_t) - i_{t-1}, \pm m)$.

Two-piece normal: $f(x) = \sqrt{2/\pi}\,(\sigma_1 + \sigma_2)^{-1}\exp\!\left(-\frac{(x-\mu)^2}{2\sigma_{1,2}^2}\right)$,
$\sigma_1 = \sigma/\sqrt{1+\gamma}$, $\sigma_2 = \sigma/\sqrt{1-\gamma}$,
$E[x] - \mu = \sqrt{2/\pi}(\sigma_2 - \sigma_1)$.

## 9. Regimes (`regimes.py`)

2×2: $\mathbb 1\{g_4 \ge g^*_4\} \times \mathbb 1\{\pi^{core} > \pi^* + 0.5\}$. Markov switching:
$x_t = \mu_{S_t} + \varepsilon_t$, $\varepsilon_t \sim N(0, \sigma^2_{S_t})$, $S_t \in \{0, 1\}$ first-order Markov.
