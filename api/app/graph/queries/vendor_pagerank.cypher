CALL algo.pageRank('Vendor', 'SUPPLIES') YIELD node, score
RETURN node.gstin AS gstin, node.legal_name AS legal_name, score
ORDER BY score DESC
LIMIT $n
