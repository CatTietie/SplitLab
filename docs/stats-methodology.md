# 统计方法文档

## 概述

SplitLab 使用**两比例 Z 检验**（Two-Proportion Z-Test）来比较实验组和对照组的转化率差异，判断差异是否具有统计显著性。

---

## 1. 转化率计算

$$
\hat{p}_i = \frac{\text{转化用户数}_i}{\text{总用户数}_i}
$$

其中 $i$ 为组别（control 或 treatment）。

---

## 2. Z 检验

### 假设

- $H_0$: $p_{\text{treatment}} = p_{\text{control}}$（无差异）
- $H_1$: $p_{\text{treatment}} \neq p_{\text{control}}$（有差异）

### 合并比例

$$
\hat{p}_{\text{pool}} = \frac{x_c + x_t}{n_c + n_t}
$$

### 标准误差

$$
SE = \sqrt{\hat{p}_{\text{pool}}(1 - \hat{p}_{\text{pool}})\left(\frac{1}{n_c} + \frac{1}{n_t}\right)}
$$

### Z 统计量

$$
Z = \frac{\hat{p}_t - \hat{p}_c}{SE}
$$

### P 值（双尾）

$$
p\text{-value} = 2 \times (1 - \Phi(|Z|))
$$

其中 $\Phi$ 为标准正态分布的 CDF。

---

## 3. 置信区间

对照组和实验组各自的 95% 置信区间：

$$
CI_i = \hat{p}_i \pm 1.96 \times \sqrt{\frac{\hat{p}_i(1-\hat{p}_i)}{n_i}}
$$

差值的置信区间：

$$
CI_{\Delta} = (\hat{p}_t - \hat{p}_c) \pm 1.96 \times \sqrt{\frac{\hat{p}_c(1-\hat{p}_c)}{n_c} + \frac{\hat{p}_t(1-\hat{p}_t)}{n_t}}
$$

---

## 4. 最小样本量

给定基线转化率 $p_1$、最小可检测效应 $\Delta$（MDE）、显著性水平 $\alpha$、统计功效 $1-\beta$：

$$
n = \left(\frac{z_{\alpha/2}\sqrt{2p_1(1-p_1)} + z_\beta\sqrt{p_1(1-p_1) + p_2(1-p_2)}}{\Delta}\right)^2
$$

其中 $p_2 = p_1 + \Delta$。

### 默认参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| $\alpha$ | 0.05 | 显著性水平（双尾） |
| $1-\beta$ | 0.80 | 统计功效 |
| MDE | 0.02 | 最小可检测效应（绝对值） |

---

## 5. 显著性判断

- **p < 0.05**：结果具有统计显著性，拒绝零假设
- **p >= 0.05**：无法拒绝零假设，差异可能由随机波动引起

### 注意事项

- 不建议在样本量未达到推荐最小样本量前做显著性判断
- 避免"偷看"（peeking）：频繁检查结果会膨胀假阳性率
- 实验至少运行一周以消除周期性效应

---

## 6. 实现

使用 `scipy.stats.norm` 进行 Z 检验计算：

```python
from scipy.stats import norm
import math

def compute_z_test(ctrl_conv, ctrl_total, treat_conv, treat_total):
    p_c = ctrl_conv / ctrl_total
    p_t = treat_conv / treat_total
    p_pool = (ctrl_conv + treat_conv) / (ctrl_total + treat_total)
    
    se = math.sqrt(p_pool * (1 - p_pool) * (1/ctrl_total + 1/treat_total))
    z = (p_t - p_c) / se
    p_value = 2 * (1 - norm.cdf(abs(z)))
    
    return z, p_value, p_value < 0.05
```

---

## 7. API 响应示例

```json
{
  "experiment_id": "uuid",
  "goal_event": "purchase",
  "groups": [
    {
      "group_name": "control",
      "total_users": 5023,
      "conversions": 502,
      "conversion_rate": 0.0999,
      "ci_lower": 0.0916,
      "ci_upper": 0.1082
    },
    {
      "group_name": "treatment",
      "total_users": 4977,
      "conversions": 747,
      "conversion_rate": 0.1501,
      "ci_lower": 0.1402,
      "ci_upper": 0.1600
    }
  ],
  "z_statistic": 7.34,
  "p_value": 0.0000,
  "is_significant": true,
  "recommended_sample_size": 3842
}
```
