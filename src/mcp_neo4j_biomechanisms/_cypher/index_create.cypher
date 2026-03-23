CREATE FULLTEXT INDEX biomechanisms_index IF NOT EXISTS
FOR (n:NeuralStructure|EdgeConfiguration|ManifoldDimension|Patient|
     FalsificationCondition|TheoreticalPrinciple|EmpiricalEvidence|Study)
ON EACH [n.name, n.description]
