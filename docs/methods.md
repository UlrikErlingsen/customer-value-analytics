# WorthSignal methods

This document records the exact formulas and conventions the app implements, with citations to the published literature each method comes from. It is the reference that the automated test suite is checked against (run `python3 -m pytest`).

Two things to keep in mind while reading:

- These are **classic, deliberately simple models**. They were chosen because they are transparent and well documented; more advanced statistical approaches exist for every problem here and are beyond this app's scope.
- Every output is an estimate built on assumptions. Treat the numbers as decision support, not truth.

**On credit:** the models documented here are the intellectual work of the researchers cited in the references — this project only implements them and claims no ownership of the theory. The project's license (AGPL) covers the code, not the mathematics.

## 1. Customer selection

*Plain language: score and rank customers so a campaign goes to the people most likely to make it profitable.*

### RFM

RFM segmentation follows classic direct-marketing practice: recency is time since the last purchase, frequency is average purchases per period, and monetary value is average amount per purchase. Score `1` is best and score `5` is worst for all three dimensions. The default is nested RFM:

1. split all customers into five equally sized recency groups;
2. within each recency group, split into five frequency groups;
3. within each recency-frequency group, split into five monetary groups.

This produces up to 125 approximately equal-sized groups and avoids the sparse combinations caused by independent scoring.

### Decision trees

Gini diversity is `2p(1-p)`. A candidate split is evaluated by the child-size-weighted Gini. The fitted tree uses this same criterion and requires a configurable minimum leaf size to reduce overfitting.

### Logistic response and targeting

For linear utility `U`, response probability is `exp(U)/(1+exp(U))`. The program reports coefficients, standard errors, Wald statistics, p-values, odds ratios, log likelihood, and predictions.

If profit on response is `vR` and profit on no response is `vN`, target when:

`p*vR + (1-p)*vN > 0`, so the break-even probability is `-vN/(vR-vN)`.

For example, with `vR=30` and `vN=-2`, the threshold is `2/32 = 6.25%`.

Lift is the response rate within a ranked group divided by the total response rate. The export contains both a running sum of per-decile lifts (a simple additive convention used in some teaching materials) and the conventional cumulative-response lift.

## 2. Customer lifetime value

*Plain language: the value of a customer today is the discounted stream of future margins, shrunk each period by the chance the customer has left.* The margin-multiple formulation follows Gupta & Lehmann (2003).

For constant margin `m`, retention `r`, discount `i`, first margin at the end of period 1, and an infinite horizon:

`CLV = m*r/(1+i-r)`.

For `T` periods:

`CLV_T = m*r/(1+i-r) * [1-(r/(1+i))^T]`.

For margin growth `g`:

`CLV = m*r/[1+i-r(1+g)]`, provided the series converges.

The margin multiple is `r/(1+i-r)`. Margin elasticity is `1`; retention elasticity is `1 + r/(1+i-r)`. Net customer value subtracts acquisition cost.

## 3. Customer equity

*Plain language: value the whole customer base by adding the value of today's customers to the discounted value of the customers you will acquire in the future.* The approach is a discrete-time simplification of Gupta, Lehmann & Stuart (2004), of the kind commonly used when teaching the model: per-period acquisition flows are backed out of the customer counts and the acquisition curve is fitted to those flows.

Observed acquired customers are reconstructed from current-customer counts:

`n_t = N_t - r*N_(t-1)`.

The bell-shaped acquisition curve, following Gupta, Lehmann & Stuart (2004), is:

`nfit_t = alpha*gamma*exp(-beta-gamma*t) / [1+exp(-beta-gamma*t)]^2`.

Parameters are estimated by nonlinear least squares. Current-customer value is `N_T*CLV`, where `N_T` is the customer count in the most recent observed period (the last row of the uploaded history; Gupta, Lehmann & Stuart write this as `N_0` because their paper places the valuation date at time zero). Future-customer value is:

`(CLV - acquisition cost) * sum_t nfit_t/(1+i)^t`.

Tax is applied to total pre-tax customer equity. For the elasticity table, an annual retention change is converted to the data period using `(1.01)^(1/periods_per_year)`. A retention scenario reconstructs historical acquisition and refits the curve before recalculating equity.

## 4. Acquisition and retention investment

*Plain language: find the acquisition and retention spend per customer that maximizes the value of a prospect, instead of assuming more retention is always better.* The model follows Blattberg & Deighton (1996).

Acquisition and retention curves are:

`a(A)=Ca*[1-exp(-beta_a*A)]`, `r(R)=Cr*[1-exp(-beta_r*R)]`.

The steepness coefficient is `beta = -ln[(C-observed rate)/C] / current spend`.

Acquired-customer value is:

`(m-A/a) + (m-R/r)*r/(1+i-r)`.

Prospect value multiplies this by acquisition probability `a`. The program numerically maximizes prospect value over acquisition and retention spend and does not assume maximum retention is optimal.

## 5. Markov switching ROI

*Plain language: model customers hopping between brands as a Markov chain, then ask whether a marketing investment that changes the hopping probabilities increases customer equity by more than it costs.* The approach follows Rust, Lemon & Zeithaml (2004).

Rows of the transition matrix are previous choices and columns are current choices. Starting from a one-hot previous choice, each future probability vector is obtained by multiplying by the transition matrix.

For company `j`, purchase occasion `t`, annual purchase frequency `f`, annual horizon `H`, amount `v`, profit margin `pi`, and annual discount `i`:

`CLV_j = sum_(t=0)^(H*f) (1+i)^(-t/f) * pi*v*B_jt`.

Change in customer equity is average change in CLV times the industry customer count. `ROI = (change in customer equity - investment)/investment`.

## 6. Contractual retention

*Plain language: in subscription businesses, retention rates typically rise over time as the churn-prone customers leave first; the shifted beta-geometric model captures this instead of assuming a constant retention rate.* The model is from Fader & Hardie (2007).

Individual defection probability `p` is beta distributed with parameters `alpha` and `beta`. The shifted beta-geometric model has:

- `Pr(T=t)=B(alpha+1,beta+t-1)/B(alpha,beta)`
- `Pr(T>t)=B(alpha,beta+t)/B(alpha,beta)`
- retention in period `t = (beta+t-1)/(alpha+beta+t-1)`

Parameters are estimated by maximum likelihood from defection counts and right-censored survivors.

## 7. BG/NBD continuous-time non-contractual model

*Plain language: when customers can buy at any moment and never announce that they've left, this model infers from each customer's purchase timing how likely they are to still be active and how much they will buy.* The model is from Fader, Hardie & Lee (2005).

Inputs are repeat frequency `x`, time of last repeat purchase `tx`, and observation length `T`. Purchase rate is gamma heterogeneous (`r`, `alpha`) and dropout probability is beta heterogeneous (`a`, `b`). The individual log likelihood follows the four-term expression in Fader, Hardie & Lee (2005) and is maximized numerically.

The probability of being active is:

`1 / {1 + I(x>0)*a/(b+x-1)*[(alpha+T)/(alpha+tx)]^(r+x)}`.

Expected future purchases use the Fader–Hardie–Lee hypergeometric expression, reported both conditional on being active and unconditional on latent activity.

## 8. BG/BB discrete-time non-contractual model

*Plain language: the same "are they still active?" question for data recorded period by period — bought or didn't buy — such as annual donations or yearly renewals.* The model is from Fader, Hardie & Shang (2010).

At the beginning of each period an alive customer drops out with probability `q`; if still alive, the customer purchases with probability `p`. Purchase probability is beta heterogeneous (`alpha`, `beta`) and dropout probability is beta heterogeneous (`gamma`, `delta`). Inputs are observed periods `n`, last-purchase period `tx`, and repeat frequency `x`.

The program evaluates the exact history likelihood as the sum of the alive-through-end path and all possible dropout paths, using beta functions and log-sum-exp for numerical stability. Pr(Alive) includes survival into the first future period. Expected future purchases are computed as an exact finite sum over future periods; this avoids the parameter-space limitation of fragile closed-form rearrangements.

## 9. Complaints and recovery

*Plain language: prepare the per-customer summaries needed by the complaint-and-recovery customer-base model, and put an upper bound on what recovering a complaining customer is worth.* The model is from Knox & van Oest (2014).

The purchase-and-complaint model family (Van Oest & Knox 2011; Knox & van Oest 2014) summarises each customer by six sufficient statistics: repeat purchases, same-day complaints, other complaints, last-event time, whether the last event involved a complaint, and observation length. The program constructs all six.

The full purchase-and-complaint model adds five heterogeneous processes and requires an 11-parameter likelihood plus simulation for predictions. Rather than substitute a rough approximation, this program limits itself to preparing the exact inputs that model needs. It implements the financial recovery rule: the maximum justified recovery cost equals `CLV if recovered - CLV if unrecovered`.

## References

- Blattberg, R. C., & Deighton, J. (1996). Manage Marketing by the Customer Equity Test. *Harvard Business Review*, 74(4), 136–144.
- Fader, P. S., & Hardie, B. G. S. (2007). How to Project Customer Retention. *Journal of Interactive Marketing*, 21(1), 76–90.
- Fader, P. S., Hardie, B. G. S., & Lee, K. L. (2005). "Counting Your Customers" the Easy Way: An Alternative to the Pareto/NBD Model. *Marketing Science*, 24(2), 275–284.
- Fader, P. S., Hardie, B. G. S., & Shang, J. (2010). Customer-Base Analysis in a Discrete-Time Noncontractual Setting. *Marketing Science*, 29(6), 1086–1108.
- Gupta, S., & Lehmann, D. R. (2003). Customers as Assets. *Journal of Interactive Marketing*, 17(1), 9–24.
- Gupta, S., Lehmann, D. R., & Stuart, J. A. (2004). Valuing Customers. *Journal of Marketing Research*, 41(1), 7–18.
- Knox, G., & van Oest, R. (2014). Customer Complaints and Recovery Effectiveness: A Customer Base Approach. *Journal of Marketing*, 78(5), 42–57.
- Rust, R. T., Lemon, K. N., & Zeithaml, V. A. (2004). Return on Marketing: Using Customer Equity to Focus Marketing Strategy. *Journal of Marketing*, 68(1), 109–127.
- Van Oest, R., & Knox, G. (2011). Extending the BG/NBD: A Simple Model of Purchases and Complaints. *International Journal of Research in Marketing*, 28(1), 30–37.
