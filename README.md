# High-Potential Content Predictor

XGBoost classifier to identify high-viral-potential tech videos before publication — built to address the editorial problem of missed high-performing content at Tencent News.

## Problem

Tech video editors rely on intuition to select topics. High-potential content is frequently overlooked because the signal is in the title semantics and channel patterns, not obvious at a glance. This model acts as a **coarse pre-filter**: flag the top 20% of candidates for priority human review, maximizing Recall to minimize miss rate.

## Data

- 6,000+ video records scraped from YouTube Data API (tech category)
- Features: title text, channel ID, publish date, view count, engagement metrics
- Label: binary — high-potential (top quartile by views within 30 days) vs. not

## Features

| Feature Group | Description |
|--------------|-------------|
| Title semantics | TF-IDF on title tokens → TruncatedSVD (50 components) for dense semantic representation |
| Channel history | Historical average views, upload frequency, channel age |
| Publish timing | Hour of day, day of week |

**Key finding from EDA**: "contrast/conflict" title framing (e.g., "X vs Y", "Why X fails") consistently correlated with viral potential across channels.

## Model

- **Algorithm**: XGBoost classifier
- **Why XGBoost over LightGBM**: Dataset size (~6k rows) doesn't require LightGBM's speed advantage; XGBoost offered finer regularization control (gamma, min_child_weight) for this feature set size
- **Why TF-IDF + SVD over embeddings**: Interpretable, fast, no external model dependency; SVD compression to 50 dims prevents overfitting on small dataset

## Results (offline validation set)

| Metric | Score |
|--------|-------|
| AUC | 0.884 |
| Recall | 84.6% |

Top-20% candidate pool captures 84.6% of actual high-potential content — meaningfully reduces editorial miss rate vs. random selection (which would capture ~20%).

## Limitations

- Training data is YouTube-scraped, not Tencent internal. Cross-platform distribution shift is a real risk in deployment.
- Model is designed as an editorial filtering tool, not a production recommender. Human review remains in the loop.
- View count label is noisy — some content goes viral days after publish due to external events.

## Requirements

```
xgboost
scikit-learn
pandas
numpy
google-api-python-client
```
