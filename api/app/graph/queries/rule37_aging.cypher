MATCH (v:Vendor)-[:ISSUED]->(i:Invoice)
WHERE i.hold_status <> 'PAID'
OPTIONAL MATCH (i)-[:POSTED_AS]->(:TallyVoucher)-[:SETTLED_BY]->(p:BankPayment)
WHERE p IS NULL
RETURN v.gstin AS gstin, v.legal_name AS vendor_name, i.id AS invoice_id,
       i.number AS invoice_number, i.date AS invoice_date, i.total AS total,
       (i.cgst + i.sgst + i.igst) AS tax
