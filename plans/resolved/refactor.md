Your job is to refactor all the python code within `scripts/*/*.py`. You shouldn't need to know much about the purpose of the project to do this, but if you do, you can look at it in `plans/current/00-overview.md` and all related plans. Now, I've noticed a lot of the python scripts don't support good type  checking due to the ambiguity around the types returned by the Airtable API. You need to reimplement this using modern python principles. Firstly, you should lean more into OOP - Instead of passing many arguments, you should be passing a few objects that store all the data. Secondly, for better type checking, instead of implementing the methods `get_table(name)` and `airtable_get(table_name, filter_formula=None)`, you should choose an approach that makes the tables' properties obvious. I recommend implementing a Database class with each table as properties, so that accessing `database.Sessions` calls the property to get the sessions table. Furthermore, you should use type-hinting where the types of objects are not obvious. And lastly, if a function name is too long for a single line, you should wrap like this:
```
def example(
    arg1, arg2,
    ...,
    argN
):
```
As opposed to this:
```
def example(arg1, arg2,
            ...,
            argN):
```

Do not change the underlying business logic unless necessary to satisfy the new architecture.
Ensure all changes are type-hinted correctly.
Please process this in chunks and summarize changes after each step