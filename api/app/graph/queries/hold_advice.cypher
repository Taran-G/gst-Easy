MATCH (v:Vendor)-[:ISSUED]->(i:Invoice)
WHERE i.hold_status IS NULL OR i.hold_status <> 'PAID'
OPTIONAL MATCH (i)-[:REFLECTED_IN]->(e:GSTR2BEntry)
OPTIONAL MATCH (v)-[:HAS_STATUS]->(f:FilingStatus {form: 'GSTR3B', period: $period})
RETURN v.gstin, v.gstin_status, v.filing_freq, i.id, i.total, (i.cgst + i.sgst + i.igst) AS tax,
       e IS NOT NULL AS in_2b, f.status AS gstr3b_status
