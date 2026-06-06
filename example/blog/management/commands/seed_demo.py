from django.core.management.base import BaseCommand

from blog.models import Post

POSTS = [
    ("Chocolate Lava Cake", "chocolate-lava-cake",
     "<p>A decadent <strong>chocolate</strong> dessert with a molten center. "
     "Use dark cocoa, butter, eggs, and a touch of espresso for depth. Bake hot and fast "
     "so the edges set while the middle stays liquid.</p>"),
    ("Classic Margherita Pizza", "margherita-pizza",
     "<p>Naples-style pizza with San Marzano tomatoes, fresh mozzarella, and basil. "
     "A blistered, chewy crust from a very hot oven is the secret to authentic flavor.</p>"),
    ("Vegetable Stir Fry", "vegetable-stir-fry",
     "<p>A quick weeknight stir fry with broccoli, peppers, snap peas, and a ginger-garlic "
     "soy sauce. Keep the heat high and the vegetables crisp for the best texture.</p>"),
    ("Sourdough Bread Basics", "sourdough-bread",
     "<p>Learn the fundamentals of sourdough: building a starter, autolyse, bulk fermentation, "
     "shaping, and a long cold proof for a tangy, open crumb and crackling crust.</p>"),
    ("Thai Green Curry", "thai-green-curry",
     "<p>Fragrant green curry with coconut milk, lemongrass, kaffir lime, and Thai basil. "
     "Balance salty fish sauce, sweet palm sugar, and bright lime for a layered broth.</p>"),
    ("Caesar Salad", "caesar-salad",
     "<p>Crisp romaine tossed with a creamy anchovy-garlic dressing, parmesan, and croutons. "
     "A coddled egg and good olive oil make the dressing silky and rich.</p>"),
]


class Command(BaseCommand):
    help = "Seed demo blog posts."

    def handle(self, *args, **options):
        for title, slug, body in POSTS:
            Post.objects.update_or_create(slug=slug, defaults={"title": title, "body": body})
        self.stdout.write(self.style.SUCCESS(f"Seeded {len(POSTS)} posts."))
