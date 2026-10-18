MATCH (v:Vendor {gstin: $gstin})
OPTIONAL MATCH (v)-[:ISSUED]->(d:Invoice {number_norm: $inv_no, fy: $fy})
OPTIONAL MATCH (v)-[:MAPS_TO_LEDGER]->(tl:TallyLedger)
OPTIONAL MATCH (v)-[:SUPPLIES_ITEM]->(vi:VendorItem {raw_name: $raw_item})-[:MAPS_TO_STOCK_ITEM]->(si1:TallyStockItem)
OPTIONAL MATCH (si2:TallyStockItem {name: $raw_item})
WITH v, d, tl, coalesce(si1, si2) AS si
OPTIONAL MATCH (r:ApprovalRule {active: true})-[:GOVERNS]->(v)
RETURN d IS NOT NULL AS is_duplicate, tl.name AS ledger, si.name AS stock_item, si.uom AS uom, collect(r.params) AS rules

