from core.parser import parse_requirement

def main():

    requirement = "Username must be unique. Password must be between 8 and 20 characters. Password must include uppercase, lowercase and digits."

    result = parse_requirement(requirement)

    print(result)


if __name__ == "__main__":
    main()