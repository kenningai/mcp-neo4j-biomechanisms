MERGE (n:`__label__` {name: $name})
ON CREATE SET n.t_created = datetime(),
              n.description = $description
ON MATCH SET  n.description = $description
__extra_sets__
RETURN n.name AS name, labels(n)[0] AS type, n.t_created AS t_created
