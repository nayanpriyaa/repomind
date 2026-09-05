from repomind.scanner import scan_repository


def main() -> None:
    repository = input("Repository path: ").strip()

    files = scan_repository(repository)

    print(f"\nFound {len(files)} files:\n")

    for file in files:
        print(file)


if __name__ == "__main__":
    main()