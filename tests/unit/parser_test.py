import json

from core.parser import parse_requirement

def main():

    requirement = '''Product name must be unique.

Product name must not be empty.

Product price must be greater than 0.

Product stock must be a non-negative integer.

Product description length must not exceed 500 characters.

System must reject creation of products with duplicate names.

System must reject products with negative stock.

System must reject products with invalid price values.

System must allow retrieving all available products.

System must allow retrieving product details using product ID.

System must return error if product ID does not exist.

System must allow updating existing product information.

System must allow deleting existing products.'''

    result = parse_requirement(requirement)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()