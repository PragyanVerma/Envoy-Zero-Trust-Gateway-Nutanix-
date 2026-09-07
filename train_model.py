import pandas as pd
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score
import joblib
import os

def create_synthetic_data(n_samples=300):
    np.random.seed(42)
    
    request_rate = np.random.uniform(0, 20, n_samples)
    is_sensitive = np.random.choice([0, 1], n_samples, p=[0.8, 0.2])
    hour_of_day = np.random.randint(0, 24, n_samples)
    
    labels = np.where((request_rate < 8) & (is_sensitive == 0), 1, 0)
    
    noise = np.random.choice([0, 1], n_samples, p=[0.9, 0.1])
    labels = np.logical_xor(labels, noise).astype(int)
    
    df = pd.DataFrame({
        'request_rate': request_rate,
        'is_sensitive_endpoint': is_sensitive,
        'hour_of_day': hour_of_day,
        'label': labels
    })
    
    return df

def train():
    df = create_synthetic_data()
    X = df[['request_rate', 'is_sensitive_endpoint', 'hour_of_day']]
    y = df['label']
    
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    model = LogisticRegression()
    model.fit(X_train, y_train)
    
    preds = model.predict(X_test)
    acc = accuracy_score(y_test, preds)
    print(f"Model trained. Accuracy on test split: {acc:.2f}")
    
    if not os.path.exists('auth-service'):
        os.makedirs('auth-service')
    joblib.dump(model, 'auth-service/trust_model.pkl')
    print("Model saved to auth-service/trust_model.pkl")

if __name__ == "__main__":
    train()
