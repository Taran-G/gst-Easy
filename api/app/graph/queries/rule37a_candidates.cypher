MATCH (v:Vendor)-[:ISSUED]->(i:Invoice {fy: $fy})
OPTIONAL MATCH (v)-[:HAS_STATUS]->(f:FilingStatus {form: 'GSTR3B', period: $period})
WHERE f.status = 'NOT_FILED' OR f IS NULL
RETURN v.gstin AS gstin, v.legal_name AS vendor_name, i.id AS invoice_id,
       i.number AS invoice_number, i.total AS total,
       (i.cgst + i.sgst + i.igst) AS reversal_amount
