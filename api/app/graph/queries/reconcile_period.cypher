MATCH (v:Vendor)-[:ISSUED]->(i:Invoice)
WHERE i.date >= $from_date AND i.date <= $to_date
OPTIONAL MATCH (i)-[:REFLECTED_IN]->(e:GSTR2BEntry {period: $period})
RETURN v.gstin AS supplier_gstin, v.legal_name AS supplier_name, v.filing_freq AS filing_freq,
       i.id AS invoice_id, i.number AS invoice_number, i.number_norm AS number_norm, i.date AS invoice_date,
       i.taxable AS taxable, (i.cgst + i.sgst + i.igst) AS tax, i.total AS total,
       e.taxable AS gstr2b_taxable, e.tax AS gstr2b_tax, e.period AS gstr2b_period
