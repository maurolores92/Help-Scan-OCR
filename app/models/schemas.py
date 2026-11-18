from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class DocumentArticleItem(BaseModel):
    codigo: Optional[str] = None
    nombre: str
    cantidad: Optional[float] = None
    precioSinIva: Optional[float] = Field(None, alias="precio_sin_iva")
    precioFinal: Optional[float] = Field(None, alias="precio_final")
    ivaPorcentaje: Optional[float] = Field(None, alias="iva_porcentaje")

    class Config:
        populate_by_name = True


class ExtractionRequest(BaseModel):
    file_path: Optional[str] = Field(None, alias="filePath")
    original_name: Optional[str] = Field(None, alias="originalName")
    company_id: Optional[int] = Field(None, alias="companyId")

    class Config:
        populate_by_name = True


class ExtractionResponse(BaseModel):
    documentType: str = Field("otro", alias="document_type")
    summary: str
    documentNumber: Optional[str] = Field(None, alias="document_number")
    documentDate: Optional[str] = Field(None, alias="document_date")
    dueDate: Optional[str] = Field(None, alias="due_date")
    issuerName: Optional[str] = Field(None, alias="issuer_name")
    issuerTaxId: Optional[str] = Field(None, alias="issuer_tax_id")
    recipientName: Optional[str] = Field(None, alias="recipient_name")
    recipientTaxId: Optional[str] = Field(None, alias="recipient_tax_id")
    recipientPhone: Optional[str] = Field(None, alias="recipient_phone")
    recipientEmail: Optional[str] = Field(None, alias="recipient_email")
    deliveryAddress: Optional[str] = Field(None, alias="delivery_address")
    responsiblePerson: Optional[str] = Field(None, alias="responsible_person")
    currency: Optional[str] = None
    netAmount: Optional[float] = Field(None, alias="net_amount")
    taxAmount: Optional[float] = Field(None, alias="tax_amount")
    totalAmount: Optional[float] = Field(None, alias="total_amount")
    paymentTerms: Optional[str] = Field(None, alias="payment_terms")
    paymentMethod: Optional[str] = Field(None, alias="payment_method")
    referenceNumber: Optional[str] = Field(None, alias="reference_number")
    cae: Optional[str] = None
    taxCondition: Optional[str] = Field(None, alias="tax_condition")
    equipmentId: Optional[str] = Field(None, alias="equipment_id")
    equipmentModel: Optional[str] = Field(None, alias="equipment_model")
    meterCount: Optional[str] = Field(None, alias="meter_count")
    tags: List[str] = []
    items: List[DocumentArticleItem] = Field(default_factory=list)
    extractedData: Dict[str, Any] = Field(default_factory=dict, alias="extracted_data")
    rawText: str = Field("", alias="raw_text")
    pageCount: int = Field(1, alias="page_count")
    aiConfidence: float = Field(0.95, alias="ai_confidence")
    extractionEngine: str = Field("python_ocr", alias="extraction_engine")
    tokensUsed: int = Field(0, alias="tokens_used")

    class Config:
        populate_by_name = True
