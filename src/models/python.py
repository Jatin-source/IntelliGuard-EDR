import xgboost as xgb
import numpy as np

print("Testing GPU connection...")
X = np.random.rand(50, 10)
y = np.random.randint(2, size=50)
dtrain = xgb.DMatrix(X, label=y)

params = {'tree_method': 'hist', 'device': 'cuda'}

try:
    xgb.train(params, dtrain, num_boost_round=1)
    print("✅ SUCCESS: XGBoost is successfully talking to your GTX 1650!")
except Exception as e:
    print("❌ ERROR: XGBoost cannot see your GPU!")
    print(e)