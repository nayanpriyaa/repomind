from dataclasses import dataclass


def standalone_function():
    print("hello")


@dataclass
class User:

    name: str

    def get_name(self):
        return self.name

    def logout(self):
        print("logout")