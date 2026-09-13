# Modelos

O detector de veículos usa pesos COCO do Ultralytics (download no primeiro uso).
Para placas, forneça `plate.pt`, treinado especificamente para detectar placas,
e habilite `OCR_ENABLED=true`. Pesos COCO **não detectam placas**.
O PaddleOCR baixa o modelo de reconhecimento no primeiro uso. Em ambiente sem
internet, provisione os pesos e caches antes da execução.

