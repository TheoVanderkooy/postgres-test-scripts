SELECT
   supp_nation,
   cust_nation,
   l_year,
   SUM(volume) AS revenue
FROM
   (
	  SELECT
		 n1.n_name AS supp_nation,
		 n2.n_name AS cust_nation,
		 EXTRACT(YEAR
	  FROM
		 l_shipdate) AS l_year,
		 l_extendedprice * (1 - l_discount) AS volume
	  FROM
		 supplier,
		 lineitem,
		 orders,
		 customer,
		 nation n1,
		 nation n2
	  WHERE
		 s_suppkey = l_suppkey
		 AND o_orderkey = l_orderkey
		 AND c_custkey = o_custkey
		 AND s_nationkey = n1.n_nationkey
		 AND c_nationkey = n2.n_nationkey
		 AND
		 (
			(n1.n_name = 'CANADA' AND n2.n_name = 'GERMANY') --- 2 choices from set of nations
			OR
			(n1.n_name = 'GERMANY' AND n2.n_name = 'CANADA') --- same 2 in opposite order
		 )
		 AND l_shipdate BETWEEN DATE '1995-01-01' AND DATE '1996-12-31'
   )
   AS shipping
GROUP BY
   supp_nation,
   cust_nation,
   l_year
ORDER BY
   supp_nation,
   cust_nation,
   l_year