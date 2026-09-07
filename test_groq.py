from config import client

models = client.models.list()

for model in models.data:
    print(model.id)