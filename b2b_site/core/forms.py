# core/forms.py

from django import forms

class ExcelUploadForm(forms.Form):
    UPLOAD_CHOICES = [
        ('stock', '库存更新 (Stock Qty)'),
        ('spec', '规格/价格更新 (Spec & Price)'),
        ('procurement', '采购在途更新 (Incoming Stock)'),
    ]

    upload_type = forms.ChoiceField(choices=UPLOAD_CHOICES, label="导入类型 / Upload Type")
    file = forms.FileField(label="选择Excel文件 / Select File")